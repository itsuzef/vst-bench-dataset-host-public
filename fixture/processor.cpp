#include "fixture/processor.h"

#include "fixture/ids.h"
#include "pluginterfaces/vst/ivstevents.h"
#include "pluginterfaces/vst/ivstparameterchanges.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <vector>

namespace MethodFixture {
namespace {

constexpr double kPi = 3.141592653589793238462643383279502884;

struct TimedEvent {
  Steinberg::int32 offset;
  Steinberg::Vst::Event event;
};

} // namespace

Processor::Processor() { setControllerClass(kControllerUid); }

Steinberg::FUnknown *Processor::create(void *) {
  return static_cast<Steinberg::Vst::IAudioProcessor *>(new Processor());
}

Steinberg::tresult PLUGIN_API
Processor::initialize(Steinberg::FUnknown *context) {
  using namespace Steinberg;
  using namespace Steinberg::Vst;

  if (AudioEffect::initialize(context) != kResultOk) {
    return kResultFalse;
  }
  addAudioOutput(STR16("Stereo Output"), SpeakerArr::kStereo);
  addEventInput(STR16("MIDI Input"), 1);
  return kResultOk;
}

Steinberg::tresult PLUGIN_API Processor::setBusArrangements(
    Steinberg::Vst::SpeakerArrangement *, Steinberg::int32 num_inputs,
    Steinberg::Vst::SpeakerArrangement *outputs, Steinberg::int32 num_outputs) {
  using namespace Steinberg;
  using namespace Steinberg::Vst;

  if (num_inputs != 0 || num_outputs != 1 || outputs == nullptr ||
      outputs[0] != SpeakerArr::kStereo) {
    return kResultFalse;
  }
  return AudioEffect::setBusArrangements(nullptr, 0, outputs, num_outputs);
}

Steinberg::tresult PLUGIN_API
Processor::canProcessSampleSize(Steinberg::int32 symbolic_sample_size) {
  return symbolic_sample_size == Steinberg::Vst::kSample32
             ? Steinberg::kResultTrue
             : Steinberg::kResultFalse;
}

void Processor::reset() {
  for (auto &voice : voices_) {
    voice = {};
  }
}

Steinberg::tresult PLUGIN_API Processor::setActive(Steinberg::TBool state) {
  reset();
  return AudioEffect::setActive(state);
}

Steinberg::tresult PLUGIN_API Processor::setProcessing(Steinberg::TBool state) {
  if (state) {
    reset();
  }
  return Steinberg::kResultOk;
}

void Processor::applyParameterChanges(
    Steinberg::Vst::IParameterChanges *changes) {
  if (changes == nullptr) {
    return;
  }
  for (Steinberg::int32 i = 0; i < changes->getParameterCount(); ++i) {
    auto *queue = changes->getParameterData(i);
    if (queue == nullptr || queue->getPointCount() < 1) {
      continue;
    }
    Steinberg::int32 sample_offset = 0;
    Steinberg::Vst::ParamValue value = 0.0;
    if (queue->getPoint(queue->getPointCount() - 1, sample_offset, value) !=
        Steinberg::kResultTrue) {
      continue;
    }
    const auto id = queue->getParameterId();
    if (id < values_.size()) {
      values_[id] = std::clamp(value, 0.0, 1.0);
    }
  }
}

float Processor::sampleVoice(int pitch, Voice &voice) {
  const int octave =
      static_cast<int>(std::floor(values_[kOctave] * 4.0 + 0.5)) - 2;
  const int shifted_pitch = std::clamp(pitch + 12 * octave, 0, 127);
  const double frequency =
      440.0 * std::pow(2.0, (static_cast<double>(shifted_pitch) - 69.0) / 12.0);

  const int waveform =
      static_cast<int>(std::floor(values_[kWaveform] * 2.0 + 0.5));
  float sample = 0.0F;
  if (waveform == 0) {
    sample = static_cast<float>(std::sin(2.0 * kPi * voice.phase));
  } else if (waveform == 1) {
    const double pulse_width = 0.1 + 0.8 * values_[kTone];
    sample = voice.phase < pulse_width ? 1.0F : -1.0F;
  } else {
    sample = static_cast<float>(4.0 * std::abs(voice.phase - 0.5) - 1.0);
  }

  voice.phase += frequency / processSetup.sampleRate;
  voice.phase -= std::floor(voice.phase);
  return sample * voice.velocity;
}

Steinberg::tresult PLUGIN_API
Processor::process(Steinberg::Vst::ProcessData &data) {
  using namespace Steinberg;
  using namespace Steinberg::Vst;

  applyParameterChanges(data.inputParameterChanges);
  if (data.symbolicSampleSize != kSample32 || data.numOutputs != 1 ||
      data.outputs == nullptr || data.outputs[0].numChannels != 2) {
    return kResultFalse;
  }

  std::vector<TimedEvent> events;
  if (data.inputEvents != nullptr) {
    events.reserve(static_cast<std::size_t>(data.inputEvents->getEventCount()));
    for (int32 i = 0; i < data.inputEvents->getEventCount(); ++i) {
      Event event{};
      if (data.inputEvents->getEvent(i, event) == kResultTrue) {
        events.push_back({event.sampleOffset, event});
      }
    }
    std::stable_sort(events.begin(), events.end(),
                     [](const TimedEvent &left, const TimedEvent &right) {
                       return left.offset < right.offset;
                     });
  }

  auto *left = data.outputs[0].channelBuffers32[0];
  auto *right = data.outputs[0].channelBuffers32[1];
  std::size_t event_index = 0;
  bool any_nonzero = false;

  for (int32 sample_index = 0; sample_index < data.numSamples; ++sample_index) {
    while (event_index < events.size() &&
           events[event_index].offset == sample_index) {
      const auto &event = events[event_index].event;
      if (event.type == Event::kNoteOnEvent && event.noteOn.pitch >= 0 &&
          event.noteOn.pitch < 128) {
        auto &voice = voices_[static_cast<std::size_t>(event.noteOn.pitch)];
        voice.phase = 0.0;
        voice.velocity = std::clamp(event.noteOn.velocity, 0.0F, 1.0F);
        voice.active = event.noteOn.velocity > 0.0F;
      } else if (event.type == Event::kNoteOffEvent &&
                 event.noteOff.pitch >= 0 && event.noteOff.pitch < 128) {
        voices_[static_cast<std::size_t>(event.noteOff.pitch)].active = false;
      }
      ++event_index;
    }

    float mixed = 0.0F;
    int active_count = 0;
    if (values_[kEnabled] >= 0.5) {
      for (int pitch = 0; pitch < 128; ++pitch) {
        auto &voice = voices_[static_cast<std::size_t>(pitch)];
        if (voice.active) {
          mixed += sampleVoice(pitch, voice);
          ++active_count;
        }
      }
    }
    if (active_count > 0) {
      mixed /= static_cast<float>(active_count);
    }
    mixed *= static_cast<float>(0.2 * values_[kGain]);
    left[sample_index] = mixed;
    right[sample_index] = mixed;
    any_nonzero = any_nonzero || mixed != 0.0F;
  }

  data.outputs[0].silenceFlags =
      any_nonzero ? 0 : std::numeric_limits<Steinberg::uint64>::max();
  return kResultOk;
}

} // namespace MethodFixture
