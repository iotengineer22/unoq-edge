cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(unoq-spicam)

# Define Edge Impulse Static Allocation to avoid heap allocation
zephyr_compile_definitions(EI_CLASSIFIER_ALLOCATION_STATIC)

target_sources(app PRIVATE src/main.cpp)

# Include paths for Edge Impulse model, parameters & SDK parent directory
target_include_directories(app PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/model-parameters
    ${CMAKE_CURRENT_SOURCE_DIR}/tflite-model
)

# Model compiled C++ sources
target_sources(app PRIVATE
    tflite-model/tflite_learn_1061869_5_compiled.cpp
)

# Add Edge Impulse SDK sources and configurations
add_subdirectory(edge-impulse-sdk/cmake/zephyr)
