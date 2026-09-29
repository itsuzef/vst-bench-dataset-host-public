#include "fixture/ids.h"

#include "pluginterfaces/base/funknown.h"
#include "pluginterfaces/vst/ivstaudioprocessor.h"
#include "pluginterfaces/vst/ivstcomponent.h"
#include "pluginterfaces/vst/ivsteditcontroller.h"
#include "public.sdk/source/vst/hosting/eventlist.h"
#include "public.sdk/source/vst/hosting/module.h"
#include "public.sdk/source/vst/hosting/parameterchanges.h"
#include "public.sdk/source/vst/hosting/plugprovider.h"
#include "public.sdk/source/vst/hosting/processdata.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

using Steinberg::int32;
using Steinberg::Vst::IAudioProcessor;
using Steinberg::Vst::IComponent;
using Steinberg::Vst::IEditController;

struct Parameter {
  Steinberg::Vst::ParamID id = 0;
  double value = 0.0;
};

struct MidiEvent {
  int32 offset = 0;
  bool note_on = false;
  int32 channel = 0;
  int32 pitch = 0;
  float velocity = 0.0F;
};

struct Request {
  int32 sample_rate = 0;
  int32 num_samples = 0;
  std::vector<Parameter> parameters;
  std::vector<MidiEvent> events;
};

struct Plugin {
  VST3::Hosting::Module::Ptr module;
  Steinberg::IPtr<Steinberg::Vst::PlugProvider> provider;
  Steinberg::OPtr<IComponent> component;
  Steinberg::OPtr<IEditController> controller;
  Steinberg::IPtr<IAudioProcessor> processor;
  VST3::Hosting::ClassInfo class_info;
  std::string vendor;
};

std::string jsonEscape(const std::string &input) {
  std::string output;
  for (const char character : input) {
    switch (character) {
    case '\\':
      output += "\\\\";
      break;
    case '"':
      output += "\\\"";
      break;
    case '\n':
      output += "\\n";
      break;
    case '\r':
      output += "\\r";
      break;
    case '\t':
      output += "\\t";
      break;
    default:
      if (static_cast<unsigned char>(character) < 0x20U) {
        throw std::runtime_error("unsupported control character");
      }
      output += character;
    }
  }
  return output;
}

Plugin loadPlugin(const std::string &path) {
  std::string error;
  auto module = VST3::Hosting::Module::create(path, error);
  if (!module) {
    throw std::runtime_error("could not load VST3 module: " + error);
  }

  const auto factory = module->getFactory();
  for (const auto &class_info : factory.classInfos()) {
    if (class_info.category() != kVstAudioEffectClass) {
      continue;
    }
    auto provider = Steinberg::owned(
        new Steinberg::Vst::PlugProvider(factory, class_info, true));
    Steinberg::OPtr<IComponent> component = provider->getComponent();
    Steinberg::OPtr<IEditController> controller = provider->getController();
    auto processor = Steinberg::U::cast<IAudioProcessor>(component);
    if (!component || !controller || !processor) {
      throw std::runtime_error(
          "fixture does not expose component, controller, and processor");
    }
    return {
        std::move(module),       std::move(provider),  std::move(component),
        std::move(controller),   std::move(processor), class_info,
        factory.info().vendor(),
    };
  }
  throw std::runtime_error("VST3 module contains no audio-effect class");
}

Request readRequest(const std::string &path) {
  std::ifstream source(path);
  if (!source) {
    throw std::runtime_error("cannot open render request");
  }

  Request request;
  std::string token;
  if (!(source >> token) || token != "MFIXTURE/1") {
    throw std::runtime_error("malformed render request header");
  }

  while (source >> token) {
    if (token == "sample_rate") {
      source >> request.sample_rate;
    } else if (token == "num_samples") {
      source >> request.num_samples;
    } else if (token == "param") {
      Parameter parameter;
      source >> parameter.id >> parameter.value;
      request.parameters.push_back(parameter);
    } else if (token == "event") {
      MidiEvent event;
      std::string type;
      source >> event.offset >> type >> event.channel >> event.pitch >>
          event.velocity;
      if (type == "note_on") {
        event.note_on = true;
      } else if (type == "note_off") {
        event.note_on = false;
      } else {
        throw std::runtime_error("unsupported MIDI event type");
      }
      request.events.push_back(event);
    } else {
      throw std::runtime_error("unknown render request field: " + token);
    }
    if (!source) {
      throw std::runtime_error("malformed render request value");
    }
  }

  if (request.sample_rate < 1 || request.num_samples < 1) {
    throw std::runtime_error("sample_rate and num_samples must be positive");
  }
  if (request.parameters.size() != MethodFixture::kParameterCount) {
    throw std::runtime_error("render request must bind all fixture parameters");
  }

  std::array<bool, MethodFixture::kParameterCount> seen{};
  for (const auto &parameter : request.parameters) {
    if (parameter.id >= MethodFixture::kParameterCount ||
        parameter.value < 0.0 || parameter.value > 1.0 || seen[parameter.id]) {
      throw std::runtime_error(
          "render request has invalid or duplicate parameter");
    }
    seen[parameter.id] = true;
  }
  for (const auto &event : request.events) {
    if (event.offset < 0 || event.offset >= request.num_samples ||
        event.channel < 0 || event.channel > 15 || event.pitch < 0 ||
        event.pitch > 127 || event.velocity < 0.0F || event.velocity > 1.0F) {
      throw std::runtime_error("render request has invalid MIDI event");
    }
  }
  return request;
}

void writeU16(std::ostream &target, std::uint16_t value) {
  const std::array<char, 2> bytes{{
      static_cast<char>(value & 0xffU),
      static_cast<char>((value >> 8U) & 0xffU),
  }};
  target.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

void writeU32(std::ostream &target, std::uint32_t value) {
  const std::array<char, 4> bytes{{
      static_cast<char>(value & 0xffU),
      static_cast<char>((value >> 8U) & 0xffU),
      static_cast<char>((value >> 16U) & 0xffU),
      static_cast<char>((value >> 24U) & 0xffU),
  }};
  target.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
}

std::int16_t quantize(float sample) {
  const double scaled =
      static_cast<double>(std::clamp(sample, -1.0F, 1.0F)) * 32767.0;
  const double rounded =
      scaled >= 0.0 ? std::floor(scaled + 0.5) : std::ceil(scaled - 0.5);
  return static_cast<std::int16_t>(rounded);
}

void writeWav(const std::string &path, int32 sample_rate, const float *left,
              const float *right, int32 num_samples) {
  const std::uint32_t data_bytes =
      static_cast<std::uint32_t>(num_samples) * 2U * sizeof(std::int16_t);
  std::ofstream target(path, std::ios::binary);
  if (!target) {
    throw std::runtime_error("cannot create output WAV");
  }

  target.write("RIFF", 4);
  writeU32(target, 36U + data_bytes);
  target.write("WAVE", 4);
  target.write("fmt ", 4);
  writeU32(target, 16U);
  writeU16(target, 1U);
  writeU16(target, 2U);
  writeU32(target, static_cast<std::uint32_t>(sample_rate));
  writeU32(target,
           static_cast<std::uint32_t>(sample_rate) * 2U * sizeof(std::int16_t));
  writeU16(target, 2U * sizeof(std::int16_t));
  writeU16(target, 16U);
  target.write("data", 4);
  writeU32(target, data_bytes);

  for (int32 index = 0; index < num_samples; ++index) {
    writeU16(target, static_cast<std::uint16_t>(quantize(left[index])));
    writeU16(target, static_cast<std::uint16_t>(quantize(right[index])));
  }
  if (!target) {
    throw std::runtime_error("failed while writing output WAV");
  }
}

void inspect(const std::string &path) {
  const auto plugin = loadPlugin(path);
  std::cout << "{\"class_uid\":\""
            << jsonEscape(plugin.class_info.ID().toString()) << "\",\"name\":\""
            << jsonEscape(plugin.class_info.name()) << "\",\"vendor\":\""
            << jsonEscape(plugin.vendor) << "\",\"parameter_count\":"
            << plugin.controller->getParameterCount() << ",\"sdk_commit\":\""
            << METHOD_FIXTURE_SDK_COMMIT << "\"}\n";
}

void render(const std::string &plugin_path, const std::string &request_path,
            const std::string &output_path) {
  using namespace Steinberg;
  using namespace Steinberg::Vst;

  const Request request = readRequest(request_path);
  auto plugin = loadPlugin(plugin_path);

  SpeakerArrangement output_arrangement = SpeakerArr::kStereo;
  if (plugin.processor->setBusArrangements(nullptr, 0, &output_arrangement,
                                           1) != kResultOk) {
    throw std::runtime_error("fixture rejected stereo output arrangement");
  }
  if (plugin.component->activateBus(kAudio, kOutput, 0, true) != kResultOk ||
      plugin.component->activateBus(kEvent, kInput, 0, true) != kResultOk) {
    throw std::runtime_error("fixture bus activation failed");
  }

  ProcessSetup setup{};
  setup.processMode = kOffline;
  setup.symbolicSampleSize = kSample32;
  setup.maxSamplesPerBlock = request.num_samples;
  setup.sampleRate = request.sample_rate;
  if (plugin.processor->setupProcessing(setup) != kResultOk) {
    throw std::runtime_error("fixture processing setup failed");
  }

  HostProcessData data;
  if (!data.prepare(*plugin.component, request.num_samples, kSample32)) {
    throw std::runtime_error("could not allocate fixture process buffers");
  }
  data.processMode = kOffline;
  data.symbolicSampleSize = kSample32;
  data.numSamples = request.num_samples;

  ParameterChanges parameter_changes(
      static_cast<int32>(MethodFixture::kParameterCount));
  std::array<double, MethodFixture::kParameterCount> readback{};
  for (const auto &parameter : request.parameters) {
    if (plugin.controller->setParamNormalized(parameter.id, parameter.value) !=
        kResultOk) {
      throw std::runtime_error("controller rejected fixture parameter");
    }
    readback[parameter.id] =
        plugin.controller->getParamNormalized(parameter.id);
    int32 queue_index = 0;
    auto *queue = parameter_changes.addParameterData(parameter.id, queue_index);
    int32 point_index = 0;
    if (queue == nullptr ||
        queue->addPoint(0, parameter.value, point_index) != kResultOk) {
      throw std::runtime_error("could not queue fixture parameter");
    }
  }
  data.inputParameterChanges = &parameter_changes;

  EventList event_list(
      static_cast<int32>(std::max<std::size_t>(request.events.size(), 1U)));
  for (const auto &input : request.events) {
    Event event{};
    event.busIndex = 0;
    event.sampleOffset = input.offset;
    if (input.note_on) {
      event.type = Event::kNoteOnEvent;
      event.noteOn.channel = static_cast<int16>(input.channel);
      event.noteOn.pitch = static_cast<int16>(input.pitch);
      event.noteOn.tuning = 0.0F;
      event.noteOn.velocity = input.velocity;
      event.noteOn.length = 0;
      event.noteOn.noteId = -1;
    } else {
      event.type = Event::kNoteOffEvent;
      event.noteOff.channel = static_cast<int16>(input.channel);
      event.noteOff.pitch = static_cast<int16>(input.pitch);
      event.noteOff.tuning = 0.0F;
      event.noteOff.velocity = input.velocity;
      event.noteOff.noteId = -1;
    }
    if (event_list.addEvent(event) != kResultOk) {
      throw std::runtime_error("could not queue fixture MIDI event");
    }
  }
  data.inputEvents = &event_list;

  if (plugin.component->setActive(true) != kResultOk ||
      plugin.processor->setProcessing(true) != kResultOk) {
    throw std::runtime_error("fixture activation failed");
  }
  const tresult process_result = plugin.processor->process(data);
  plugin.processor->setProcessing(false);
  plugin.component->setActive(false);
  if (process_result != kResultOk) {
    throw std::runtime_error("fixture processing failed");
  }
  if (data.numOutputs != 1 || data.outputs == nullptr ||
      data.outputs[0].numChannels != 2) {
    throw std::runtime_error("fixture returned an invalid output layout");
  }

  writeWav(output_path, request.sample_rate,
           data.outputs[0].channelBuffers32[0],
           data.outputs[0].channelBuffers32[1], request.num_samples);

  std::cout << std::setprecision(17) << "{\"samples\":" << request.num_samples
            << ",\"readback\":[";
  for (std::size_t index = 0; index < readback.size(); ++index) {
    if (index != 0U) {
      std::cout << ",";
    }
    std::cout << readback[index];
  }
  std::cout << "]}\n";
}

} // namespace

int main(int argc, char **argv) {
  try {
    if (argc == 3 && std::string(argv[1]) == "inspect") {
      inspect(argv[2]);
      return 0;
    }
    if (argc == 5 && std::string(argv[1]) == "render") {
      render(argv[2], argv[3], argv[4]);
      return 0;
    }
    std::cerr << "usage: method_fixture_runner inspect PLUGIN\n"
              << "       method_fixture_runner render PLUGIN REQUEST OUTPUT\n";
    return 2;
  } catch (const std::exception &error) {
    std::cerr << error.what() << "\n";
    return 1;
  }
}
