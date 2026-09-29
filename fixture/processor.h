#pragma once

#include "public.sdk/source/vst/vstaudioeffect.h"

#include <array>

namespace MethodFixture {

class Processor final : public Steinberg::Vst::AudioEffect {
public:
  Processor();

  static Steinberg::FUnknown *create(void *);

  Steinberg::tresult PLUGIN_API
  initialize(Steinberg::FUnknown *context) override;
  Steinberg::tresult PLUGIN_API setBusArrangements(
      Steinberg::Vst::SpeakerArrangement *inputs, Steinberg::int32 num_inputs,
      Steinberg::Vst::SpeakerArrangement *outputs,
      Steinberg::int32 num_outputs) override;
  Steinberg::tresult PLUGIN_API
  canProcessSampleSize(Steinberg::int32 symbolic_sample_size) override;
  Steinberg::tresult PLUGIN_API setActive(Steinberg::TBool state) override;
  Steinberg::tresult PLUGIN_API setProcessing(Steinberg::TBool state) override;
  Steinberg::tresult PLUGIN_API
  process(Steinberg::Vst::ProcessData &data) override;

private:
  struct Voice {
    double phase = 0.0;
    float velocity = 0.0F;
    bool active = false;
  };

  void reset();
  void applyParameterChanges(Steinberg::Vst::IParameterChanges *changes);
  float sampleVoice(int pitch, Voice &voice);

  std::array<double, 6> values_{{0.5, 0.5, 0.0, 0.5, 1.0, 0.5}};
  std::array<Voice, 128> voices_{};
};

} // namespace MethodFixture
