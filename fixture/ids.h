#pragma once

#include "pluginterfaces/base/funknown.h"
#include "pluginterfaces/vst/vsttypes.h"

namespace MethodFixture {

enum ParameterId : Steinberg::Vst::ParamID {
  kGain = 0,
  kTone = 1,
  kWaveform = 2,
  kOctave = 3,
  kEnabled = 4,
  kControlOnly = 5,
  kParameterCount = 6,
};

static const Steinberg::FUID kProcessorUid(0x5F94B1C2, 0x7A624DF0, 0xA910B2D3,
                                           0x64E0F871);
static const Steinberg::FUID kControllerUid(0xFA01C7E5, 0x3D194B61, 0x8F4A27BC,
                                            0xD2096E35);

inline constexpr const char *kStableIdentifier =
    "org.example.method-fixture.v1";
inline constexpr const char *kClassUid = "5F94B1C27A624DF0A910B2D364E0F871";
inline constexpr const char *kPluginName = "Method Fixture Instrument";
inline constexpr const char *kVendorName = "Independent Method Fixture";
inline constexpr const char *kVersion = "0.1.0-private";

} // namespace MethodFixture
