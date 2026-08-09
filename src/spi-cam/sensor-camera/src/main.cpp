#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/video.h>
#include <zephyr/drivers/gpio.h>
#include <string.h>
#include <stdio.h>

// Edge Impulse Classifier
#include "edge-impulse-sdk/classifier/ei_run_classifier.h"

#define LED0_NODE DT_ALIAS(led0)
#define LED1_NODE DT_ALIAS(led1)
#define LED4_NODE DT_NODELABEL(led4_green)

static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET(LED1_NODE, gpios);
static const struct gpio_dt_spec led4_green = GPIO_DT_SPEC_GET(LED4_NODE, gpios);

// LED3 Blue channel controlled directly via GPIOH pin 12 to resolve activation issues
#define LED3_BLUE_PIN 12
static const struct device *const gpioh_dev = DEVICE_DT_GET(DT_NODELABEL(gpioh));

/* Square (320x320) - Physical resolution configured on the camera */
#define FRAME_WIDTH 320
#define FRAME_HEIGHT 320
#define PIXEL_FORMAT VIDEO_PIX_FMT_RGB565

/* Crop parameters (central 96x96 region) */
#define CROP_WIDTH 96
#define CROP_HEIGHT 96
#define IMAGE_SIZE (CROP_WIDTH * CROP_HEIGHT * 2) /* 96 * 96 * 2 = 18432 bytes */

/* Static RAM buffer for direct memory dump via OpenOCD */
uint8_t image_buffer[IMAGE_SIZE] __aligned(4);

/* Log buffer to dump inference results via OpenOCD */
char inference_log_buffer[2048] __aligned(4) = "No inference run yet";

/* Debug checkpoint to track firmware boot progress */
char boot_checkpoint[256] __aligned(4) = "0: Init";

/* PIR sensor pin configuration (D7 on Arduino Uno Q is PB2 according to datasheet) */
#define PIR_PIN 2
static const struct device *const gpiob_dev = DEVICE_DT_GET(DT_NODELABEL(gpiob));
static struct gpio_callback pir_cb_data;
K_SEM_DEFINE(pir_sem, 0, 1);

void pir_sensor_handler(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{
	k_sem_give(&pir_sem);
}

// Callback to feed data to Edge Impulse
int get_camera_data(size_t offset, size_t length, float *out_ptr)
{
    for (size_t i = 0; i < length; i++) {
        size_t pixel_idx = offset + i;

        if (pixel_idx * 2 + 1 >= IMAGE_SIZE) {
            out_ptr[i] = 0.0f;
            continue;
        }

        uint16_t b1 = image_buffer[pixel_idx * 2];
        uint16_t b2 = image_buffer[pixel_idx * 2 + 1];
        uint16_t pixel = (b1 << 8) | b2;
        
        // Extract RGB values from RGB565 (R: 5bit, G: 6bit, B: 5bit)
        uint32_t r = ((pixel >> 11) & 0x1F) << 3; // R to 8bit
        uint32_t g = ((pixel >> 5) & 0x3F) << 2;  // G to 8bit
        uint32_t b = (pixel & 0x1F) << 3;         // B to 8bit
        
        // Pack into 0x00RRGGBB format and convert to float (expected by SDK's extract_image_features)
        uint32_t packed_pixel = (r << 16) | (g << 8) | b;
        out_ptr[i] = (float)packed_pixel;
    }
    return 0;
}

extern "C" int main(void)
{
	snprintf(boot_checkpoint, sizeof(boot_checkpoint), "1: Main start");
	const struct device *const camera_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_camera));
	int ret;

	printk("\n=== Arducam Mega 160x120 QQVGA (Cropped to 96x96) Edge Impulse Test ===\n");

	/* Initialize LED pins */
	if (device_is_ready(led_green.port)) {
		gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE);
	}
	if (device_is_ready(led_red.port)) {
		gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE);
	}
	if (device_is_ready(gpioh_dev)) {
		gpio_pin_configure(gpioh_dev, LED3_BLUE_PIN, GPIO_OUTPUT_INACTIVE | GPIO_ACTIVE_LOW);
	}
	if (device_is_ready(led4_green.port)) {
		gpio_pin_configure_dt(&led4_green, GPIO_OUTPUT_INACTIVE);
	}

	if (!device_is_ready(camera_dev)) {
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Err: Camera not ready");
		printk("Camera device is not ready!\n");
		if (device_is_ready(led_red.port)) {
			gpio_pin_set_dt(&led_red, 1);
		}
		return -1;
	}
	snprintf(boot_checkpoint, sizeof(boot_checkpoint), "2: Camera ready");
	printk("Camera device %s is ready.\n", camera_dev->name);

	/* Print the address of the static image buffer */
	printk("IMAGE_BUF_ADDR: %p\n", image_buffer);

	/* Configure video format (160x120 RGB565) */
	struct video_format fmt = {
		.type = VIDEO_BUF_TYPE_OUTPUT,
		.pixelformat = PIXEL_FORMAT,
		.width = FRAME_WIDTH,
		.height = FRAME_HEIGHT,
		.pitch = FRAME_WIDTH * 2,
	};

	snprintf(boot_checkpoint, sizeof(boot_checkpoint), "3: SetFormat init");
	ret = video_set_format(camera_dev, &fmt);
	if (ret < 0) {
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Err: SetFormat failed %d", ret);
		printk("Failed to set video format: %d\n", ret);
		if (device_is_ready(led_red.port)) {
			gpio_pin_set_dt(&led_red, 1);
		}
		return ret;
	}
	snprintf(boot_checkpoint, sizeof(boot_checkpoint), "4: SetFormat success");
	printk("Set format successfully: 160x120 RGB565 (size: %u)\n", fmt.size);

	/* Allocate and enqueue video buffers */
	struct video_buffer *vbuf;
	for (int i = 0; i < 2; i++) {
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "5: Alloc video buffer %d", i);
		vbuf = video_buffer_aligned_alloc(fmt.size, 4, K_NO_WAIT);
		if (vbuf == NULL) {
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Err: Alloc buffer %d failed", i);
			printk("Unable to allocate video buffer\n");
			if (device_is_ready(led_red.port)) {
				gpio_pin_set_dt(&led_red, 1);
			}
			return -ENOMEM;
		}
		vbuf->type = VIDEO_BUF_TYPE_OUTPUT;
		ret = video_enqueue(camera_dev, vbuf);
		if (ret < 0) {
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Err: Enqueue buffer %d failed: %d", i, ret);
			printk("Failed to enqueue video buffer: %d\n", ret);
			return ret;
		}
	}

	/* Configure PIR sensor pin (D7 / PB2) as input Active Low with internal Pull-up */
	if (device_is_ready(gpiob_dev)) {
		ret = gpio_pin_configure(gpiob_dev, PIR_PIN, GPIO_INPUT | GPIO_ACTIVE_LOW | GPIO_PULL_UP);
		if (ret < 0) {
			printk("Failed to configure PIR pin: %d\n", ret);
		}
		ret = gpio_pin_interrupt_configure(gpiob_dev, PIR_PIN, GPIO_INT_EDGE_TO_ACTIVE);
		if (ret < 0) {
			printk("Failed to configure PIR interrupt: %d\n", ret);
		}
		gpio_init_callback(&pir_cb_data, pir_sensor_handler, BIT(PIR_PIN));
		ret = gpio_add_callback(gpiob_dev, &pir_cb_data);
		if (ret < 0) {
			printk("Failed to add PIR callback: %d\n", ret);
		}
		printk("PIR sensor (D7/PB2) Active Low interrupt configured successfully.\n");
	} else {
		printk("GPIOB device not ready for PIR sensor!\n");
	}
	snprintf(boot_checkpoint, sizeof(boot_checkpoint), "7: PIR init success");
	printk("PIR Sensor initialized. Event-driven capture ready.\n");

	while (1) {
		struct video_buffer *captured_buf;
		uint32_t capture_time_ms = 0;

		printk("\n=== Waiting for PIR sensor trigger... (Idle state) ===\n");
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "8: Waiting for PIR trigger");

		// Turn off all RGB LEDs while waiting for the next detection event
		if (device_is_ready(led_red.port) && device_is_ready(led_green.port)) {
			gpio_pin_set_dt(&led_red, 0);
			gpio_pin_set_dt(&led_green, 0);
		}
		if (device_is_ready(gpioh_dev)) {
			gpio_pin_set(gpioh_dev, LED3_BLUE_PIN, 0);
		}

		// Block forever until PIR sensor detects motion (GPIO interrupt triggers)
		k_sem_take(&pir_sem, K_FOREVER);
		printk("PIR Sensor triggered! Turning on camera stream...\n");

		// Toggle LED4 green state to indicate a new trigger event
		if (device_is_ready(led4_green.port)) {
			gpio_pin_toggle_dt(&led4_green);
		}

		// Start camera stream dynamically to capture the latest real-time frame
		ret = video_stream_start(camera_dev, VIDEO_BUF_TYPE_OUTPUT);
		if (ret < 0) {
			printk("Failed to start video stream: %d\n", ret);
			k_sleep(K_MSEC(500));
			continue;
		}

		/* Dequeue frame (wait for capture completion) and measure SPI capture time */
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "8: Waiting for video dequeue");
		ret = video_dequeue(camera_dev, &captured_buf, K_FOREVER);
		if (ret >= 0) {
			capture_time_ms = (uint32_t)(k_uptime_get_32() - captured_buf->timestamp);
		}
		if (ret < 0) {
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Err: Dequeue failed %d", ret);
			printk("Failed to dequeue video buffer: %d\n", ret);
			k_sleep(K_MSEC(1000));
			continue;
		}
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "9: Dequeue success (bytes used=%u)", captured_buf->bytesused);

		/* Indicator for successful capture removed to prevent interference with RGB detection color coding */

		/* Copy captured data to the static RAM buffer with 320x320 crop and 96x96 resize */
		if (captured_buf->bytesused >= (FRAME_WIDTH * FRAME_HEIGHT * 2)) {
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "10: Scaling 320x320 to 96x96");
			uint8_t *src = (uint8_t *)captured_buf->buffer;
			uint8_t *dst = image_buffer;
			
			int src_w = FRAME_WIDTH;  // 320
			int src_h = FRAME_HEIGHT; // 320
			
			// Crop 320x320 (Whole frame)
			int crop_size = 320;
			int start_x = (src_w - crop_size) / 2; // 0
			int start_y = (src_h - crop_size) / 2; // 0
			
			int target_size = 96;
			
			// Average Pooling Scaling from 320x320 crop to 96x96 target to prevent aliasing
			for (int dy = 0; dy < target_size; dy++) {
				int sy_start = start_y + (dy * crop_size) / target_size;
				int sy_end = start_y + ((dy + 1) * crop_size) / target_size;
				if (sy_end <= sy_start) sy_end = sy_start + 1;

				for (int dx = 0; dx < target_size; dx++) {
					int sx_start = start_x + (dx * crop_size) / target_size;
					int sx_end = start_x + ((dx + 1) * crop_size) / target_size;
					if (sx_end <= sx_start) sx_end = sx_start + 1;

					uint32_t sum_r = 0;
					uint32_t sum_g = 0;
					uint32_t sum_b = 0;
					uint32_t count = 0;

					for (int sy = sy_start; sy < sy_end && sy < src_h; sy++) {
						for (int sx = sx_start; sx < sx_end && sx < src_w; sx++) {
							int src_idx = (sy * src_w + sx) * 2;
							uint16_t b1 = src[src_idx];
							uint16_t b2 = src[src_idx + 1];
							uint16_t pixel = (b1 << 8) | b2;

							sum_r += ((pixel >> 11) & 0x1F) << 3;
							sum_g += ((pixel >> 5) & 0x3F) << 2;
							sum_b += (pixel & 0x1F) << 3;
							count++;
						}
					}

					if (count > 0) {
						uint8_t avg_r = (sum_r / count) >> 3; // Back to 5-bit
						uint8_t avg_g = (sum_g / count) >> 2; // Back to 6-bit
						uint8_t avg_b = (sum_b / count) >> 3; // Back to 5-bit
						uint16_t avg_pixel = (avg_r << 11) | (avg_g << 5) | avg_b;

						int dst_idx = (dy * target_size + dx) * 2;
						dst[dst_idx]     = (avg_pixel >> 8) & 0xFF;
						dst[dst_idx + 1] = avg_pixel & 0xFF;
					}
				}
			}
			printk("Captured QVGA cropped to 240x240 and resized to 96x96 in RAM!\n");

			// Run Edge Impulse inference
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "11: Run Edge Impulse classifier starting");
			signal_t signal;
			signal.total_length = EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE;
			signal.get_data = &get_camera_data;

			ei_impulse_result_t result = { 0 };
			EI_IMPULSE_ERROR ei_ret = run_classifier(&signal, &result, false);
			
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "12: Run Edge Impulse classifier finished: %d", ei_ret);

			// Format log into buffer
			char *log_ptr = inference_log_buffer;
			int log_size = sizeof(inference_log_buffer);
			int written = 0;
			
			if (ei_ret != EI_IMPULSE_OK) {
				written = snprintf(log_ptr, log_size, "Failed to run classifier (%d)\n", ei_ret);
			} else {
				written = snprintf(log_ptr, log_size, 
					"Predictions (DSP: %d ms., Classification: %d ms., Anomaly: %d ms., SPI Capture: %u ms.): \n",
					result.timing.dsp, result.timing.classification, result.timing.anomaly, capture_time_ms);
				if (written > 0 && written < log_size) {
					log_ptr += written;
					log_size -= written;
				}
#if EI_CLASSIFIER_OBJECT_DETECTION == 1
				bool found_bb = false;
				bool threshold_exceeded = false;
				for (size_t ix = 0; ix < result.bounding_boxes_count; ix++) {
					auto bb = result.bounding_boxes[ix];
					if (bb.value == 0) {
						continue;
					}
					found_bb = true;
					if (bb.value >= 0.5f) {
						threshold_exceeded = true;
					}
					written = snprintf(log_ptr, log_size, "  %s (%f) [ x: %u, y: %u, w: %u, h: %u ]\n", 
						bb.label, bb.value, bb.x, bb.y, bb.width, bb.height);
					if (written > 0 && written < log_size) {
						log_ptr += written;
						log_size -= written;
					}
				}
				if (!found_bb) {
					snprintf(log_ptr, log_size, "  No objects detected\n");
				}
				
				// Control RGB LED color depending on the detected object type with confidence >= 0.5
				uint8_t r_val = 0;
				uint8_t g_val = 0;
				uint8_t b_val = 0;

				for (size_t ix = 0; ix < result.bounding_boxes_count; ix++) {
					auto bb = result.bounding_boxes[ix];
					if (bb.value >= 0.5f) {
						if (strcmp(bb.label, "pico") == 0) {
							b_val = 1; // Blue
						} else if (strcmp(bb.label, "xiao") == 0) {
							g_val = 1; // Green
						} else if (strcmp(bb.label, "nrf54l15") == 0) {
							r_val = 1; // Red
						} else if (strcmp(bb.label, "fpc") == 0) {
							r_val = 1; g_val = 1; // Yellow (Red + Green)
						}
						break; // Set color based on the first high-confidence object
					}
				}

				if (device_is_ready(led_red.port) && device_is_ready(led_green.port)) {
					gpio_pin_set_dt(&led_red, r_val);
					gpio_pin_set_dt(&led_green, g_val);
				}
				if (device_is_ready(gpioh_dev)) {
					gpio_pin_set(gpioh_dev, LED3_BLUE_PIN, b_val);
				}
#else
				for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
					written = snprintf(log_ptr, log_size, "    %s: %.5f\n", 
						result.classification[ix].label, result.classification[ix].value);
					if (written > 0 && written < log_size) {
						log_ptr += written;
						log_size -= written;
					}
				}
#endif
			}
			// Also print to low-level console
			printk("%s", inference_log_buffer);
		} else {
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Warn: Frame too small (%u < %d)", captured_buf->bytesused, FRAME_WIDTH * FRAME_HEIGHT * 2);
			printk("Warning: captured frame size (%u) is smaller than expected 160x120\n", captured_buf->bytesused);
		}

		/* Re-enqueue the buffer for the next frame */
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "13: Re-enqueueing buffer");
		ret = video_enqueue(camera_dev, captured_buf);
		if (ret < 0) {
			snprintf(boot_checkpoint, sizeof(boot_checkpoint), "Err: Re-enqueue failed %d", ret);
			printk("Failed to re-enqueue buffer: %d\n", ret);
		}

		// Stop the camera stream dynamically to save power and clear buffers for the next event
		video_stream_stop(camera_dev, VIDEO_BUF_TYPE_OUTPUT);
		printk("Camera stream stopped. Entering idle state...\n");

		/* Keep the RGB LED status ON for 3 seconds for visual verification */
		snprintf(boot_checkpoint, sizeof(boot_checkpoint), "14: Loop sleeping 3000ms");
		k_sleep(K_MSEC(3000));
	}

	return 0;
}
