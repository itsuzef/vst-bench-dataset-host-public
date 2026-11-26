# SPDX-FileCopyrightText: 2026 Youssef Hemimy
# SPDX-License-Identifier: MIT

cmake_minimum_required(VERSION 3.25)

if(APPLE)
    project(method_fixture_demo VERSION 0.1.0 LANGUAGES CXX OBJCXX)
else()
    project(method_fixture_demo VERSION 0.1.0 LANGUAGES CXX)
endif()

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(SMTG_CREATE_PLUGIN_LINK OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VSTGUI_SUPPORT OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_PLUGIN_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES OFF CACHE BOOL "" FORCE)
set(SMTG_ENABLE_VST3_HOSTING_EXAMPLES_AUDIOHOST OFF CACHE BOOL "" FORCE)
set(SMTG_RUN_VST_VALIDATOR OFF CACHE BOOL "" FORCE)

# The VST3 SDK asks `xcodebuild` for the Xcode version and stops without one.
# With only the Command Line Tools selected there is no xcodebuild, so pass the
# SDK the installed tools' version through the variable it already honours.
if(APPLE AND NOT DEFINED ENV{XCODE_VERSION})
    execute_process(COMMAND xcodebuild -version
        RESULT_VARIABLE xcodebuild_status OUTPUT_QUIET ERROR_QUIET)
    if(NOT xcodebuild_status EQUAL 0)
        execute_process(COMMAND pkgutil --pkg-info=com.apple.pkg.CLTools_Executables
            OUTPUT_VARIABLE command_line_tools ERROR_QUIET)
        string(REGEX MATCH "version: ([0-9]+\\.[0-9]+)" _ "${command_line_tools}")
        if(NOT CMAKE_MATCH_1)
            message(FATAL_ERROR
                "Neither Xcode nor the Xcode Command Line Tools were found. "
                "Install one of them (xcode-select --install).")
        endif()
        set(XCODE_VERSION "${CMAKE_MATCH_1}")
        set(ENV{XCODE_VERSION} "${CMAKE_MATCH_1}")
        message(STATUS "Using Xcode Command Line Tools ${CMAKE_MATCH_1} (no xcodebuild)")
    endif()
endif()

include(FetchContent)
FetchContent_Declare(
    vst3sdk
    GIT_REPOSITORY https://github.com/steinbergmedia/vst3sdk.git
    GIT_TAG 3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96
    GIT_SHALLOW FALSE
    GIT_SUBMODULES base cmake pluginterfaces public.sdk
    GIT_SUBMODULES_RECURSE TRUE
)
FetchContent_MakeAvailable(vst3sdk)
set(public_sdk_SOURCE_DIR "${vst3sdk_SOURCE_DIR}/public.sdk")

smtg_add_vst3plugin(MethodFixture
    fixture/controller.cpp
    fixture/controller.h
    fixture/factory.cpp
    fixture/ids.h
    fixture/processor.cpp
    fixture/processor.h
)
target_link_libraries(MethodFixture PRIVATE sdk)
target_include_directories(MethodFixture PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(MethodFixture PRIVATE
    $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall -Wextra -Wpedantic -Werror>
)

if(SMTG_MAC)
    smtg_target_set_bundle(MethodFixture
        BUNDLE_IDENTIFIER "org.example.method-fixture"
        COMPANY_NAME "Independent Method Fixture"
    )
endif()

add_executable(method_fixture_runner
    host/runner.cpp
    ${public_sdk_SOURCE_DIR}/source/vst/hosting/plugprovider.cpp
)
if(APPLE)
    target_sources(method_fixture_runner PRIVATE
        ${public_sdk_SOURCE_DIR}/source/vst/hosting/module_mac.mm
    )
    set_source_files_properties(
        ${public_sdk_SOURCE_DIR}/source/vst/hosting/module_mac.mm
        PROPERTIES COMPILE_FLAGS "-fobjc-arc"
    )
    target_link_libraries(method_fixture_runner PRIVATE "-framework Cocoa")
elseif(UNIX)
    target_sources(method_fixture_runner PRIVATE
        ${public_sdk_SOURCE_DIR}/source/vst/hosting/module_linux.cpp
    )
elseif(WIN32)
    target_sources(method_fixture_runner PRIVATE
        ${public_sdk_SOURCE_DIR}/source/vst/hosting/module_win32.cpp
    )
endif()
target_link_libraries(method_fixture_runner PRIVATE sdk_hosting)
target_include_directories(method_fixture_runner SYSTEM PRIVATE ${vst3sdk_SOURCE_DIR})
target_include_directories(method_fixture_runner PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_definitions(method_fixture_runner PRIVATE
    METHOD_FIXTURE_SDK_COMMIT="3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96"
)
target_compile_options(method_fixture_runner PRIVATE
    $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall -Wextra -Wpedantic -Werror>
)
