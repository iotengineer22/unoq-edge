CXX ?= g++
CXXFLAGS += -O3 -Wall -g -std=c++14

# GStreamer Flags for MIPI-CSI2 Camera Streaming
GST_CFLAGS := $(shell pkg-config --cflags gstreamer-1.0 gstreamer-app-1.0)
GST_LIBS := $(shell pkg-config --libs gstreamer-1.0 gstreamer-app-1.0)

TARGET := server

all: $(TARGET)

$(TARGET): server.cpp
	@echo "[Building] Compiling server.cpp..."
	$(CXX) $(CXXFLAGS) $(GST_CFLAGS) $< -o $@ $(GST_LIBS) -pthread
	@echo "=================================================="
	@echo " Build Successful! Run with: ./server"
	@echo "=================================================="

clean:
	rm -f $(TARGET)

.PHONY: all clean
