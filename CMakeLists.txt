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
target_include_directories(method_fixture_runner PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_definitions(method_fixture_runner PRIVATE
    METHOD_FIXTURE_SDK_COMMIT="3cdf9ca5d1f5b1b21e0a86832aa4abe55607bd96"
)
target_compile_options(method_fixture_runner PRIVATE
    $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall -Wextra -Wpedantic -Werror>
)
