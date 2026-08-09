#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/video.h>
#include <zephyr/drivers/gpio.h>
#include <string.h>

#define LED0_NODE DT_ALIAS(led0)
#define LED1_NODE DT_ALIAS(led1)

static const struct gpio_dt_spec led_green = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static const struct gpio_dt_spec led_red = GPIO_DT_SPEC_GET(LED1_NODE, gpios);

/* QVGA (320x240) - Standard resolution physically supported by the camera keeping aspect ratio */
#define FRAME_WIDTH 320
#define FRAME_HEIGHT 240
#define PIXEL_FORMAT VIDEO_PIX_FMT_RGB565
#define IMAGE_SIZE (FRAME_WIDTH * FRAME_HEIGHT * 2) /* 320 * 240 * 2 = 153600 bytes */

/* Static RAM buffer for direct memory dump via OpenOCD */
uint8_t image_buffer[IMAGE_SIZE] __aligned(4);

int main(void)
{
	const struct device *const camera_dev = DEVICE_DT_GET(DT_CHOSEN(zephyr_camera));
	int ret;

	printk("\n=== Arducam Mega 320x240 QVGA Dump Test ===\n");

	/* Initialize LED pins */
	if (device_is_ready(led_green.port)) {
		gpio_pin_configure_dt(&led_green, GPIO_OUTPUT_INACTIVE);
	}
	if (device_is_ready(led_red.port)) {
		gpio_pin_configure_dt(&led_red, GPIO_OUTPUT_INACTIVE);
	}

	if (!device_is_ready(camera_dev)) {
		printk("Camera device is not ready!\n");
		if (device_is_ready(led_red.port)) {
			gpio_pin_set_dt(&led_red, 1);
		}
		return -1;
	}
	printk("Camera device %s is ready.\n", camera_dev->name);

	/* Print the address of the static image buffer (parseable by debugger scripts) */
	printk("IMAGE_BUF_ADDR: %p\n", image_buffer);

	/* Configure video format (320x240 RGB565) */
	struct video_format fmt = {
		.type = VIDEO_BUF_TYPE_OUTPUT,
		.pixelformat = PIXEL_FORMAT,
		.width = FRAME_WIDTH,
		.height = FRAME_HEIGHT,
		.pitch = FRAME_WIDTH * 2,
	};

	ret = video_set_format(camera_dev, &fmt);
	if (ret < 0) {
		printk("Failed to set video format: %d\n", ret);
		if (device_is_ready(led_red.port)) {
			gpio_pin_set_dt(&led_red, 1);
		}
		return ret;
	}
	printk("Set format successfully: 320x240 RGB565 (size: %u)\n", fmt.size);

	/* Allocate and enqueue video buffers */
	struct video_buffer *vbuf;
	for (int i = 0; i < 2; i++) {
		vbuf = video_buffer_aligned_alloc(fmt.size, 4, K_NO_WAIT);
		if (vbuf == NULL) {
			printk("Unable to allocate video buffer\n");
			if (device_is_ready(led_red.port)) {
				gpio_pin_set_dt(&led_red, 1);
			}
			return -ENOMEM;
		}
		vbuf->type = VIDEO_BUF_TYPE_OUTPUT;
		ret = video_enqueue(camera_dev, vbuf);
		if (ret < 0) {
			printk("Failed to enqueue video buffer: %d\n", ret);
			return ret;
		}
	}

	/* Start video stream */
	ret = video_stream_start(camera_dev, VIDEO_BUF_TYPE_OUTPUT);
	if (ret < 0) {
		printk("Failed to start video stream: %d\n", ret);
		return ret;
	}
	printk("Video stream started. Capturing loop starting...\n");

	while (1) {
		struct video_buffer *captured_buf;

		/* Dequeue frame (wait for capture completion) */
		ret = video_dequeue(camera_dev, &captured_buf, K_FOREVER);
		if (ret < 0) {
			printk("Failed to dequeue video buffer: %d\n", ret);
			k_sleep(K_MSEC(1000));
			continue;
		}

		/* Indicator for successful capture (toggle green LED) */
		if (device_is_ready(led_green.port)) {
			gpio_pin_toggle_dt(&led_green);
		}

		/* Copy captured data to the static RAM buffer */
		if (captured_buf->bytesused <= IMAGE_SIZE) {
			memcpy(image_buffer, captured_buf->buffer, captured_buf->bytesused);
			printk("Captured Frame copied to RAM! Size: %u bytes\n", captured_buf->bytesused);
		} else {
			printk("Warning: captured frame size (%u) exceeds buffer size\n", captured_buf->bytesused);
		}

		/* Re-enqueue the buffer for the next frame */
		ret = video_enqueue(camera_dev, captured_buf);
		if (ret < 0) {
			printk("Failed to re-enqueue buffer: %d\n", ret);
		}

		/* Wait for 3 seconds before the next capture */
		k_sleep(K_MSEC(3000));
	}

	return 0;
}
