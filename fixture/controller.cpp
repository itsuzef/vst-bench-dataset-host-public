#include "fixture/controller.h"

#include "fixture/ids.h"

namespace MethodFixture {

Steinberg::FUnknown *Controller::create(void *) {
  return static_cast<Steinberg::Vst::IEditController *>(new Controller());
}

Steinberg::tresult PLUGIN_API
Controller::initialize(Steinberg::FUnknown *context) {
  using namespace Steinberg;
  using namespace Steinberg::Vst;

  if (EditController::initialize(context) != kResultOk) {
    return kResultFalse;
  }

  constexpr int32 automate = ParameterInfo::kCanAutomate;
  parameters.addParameter(STR16("Gain"), nullptr, 0, 0.5, automate, kGain);
  parameters.addParameter(STR16("Tone"), nullptr, 0, 0.5, automate, kTone);
  parameters.addParameter(STR16("Waveform"), nullptr, 2, 0.0, automate,
                          kWaveform);
  parameters.addParameter(STR16("Octave"), nullptr, 4, 0.5, automate, kOctave);
  parameters.addParameter(STR16("Enabled"), nullptr, 1, 1.0, automate,
                          kEnabled);
  parameters.addParameter(STR16("Control Only"), nullptr, 0, 0.5, automate,
                          kControlOnly);
  return kResultOk;
}

} // namespace MethodFixture
