#include "fixture/controller.h"
#include "fixture/ids.h"
#include "fixture/processor.h"

#include "public.sdk/source/main/pluginfactory.h"

BEGIN_FACTORY_DEF(MethodFixture::kVendorName, "", "")

DEF_CLASS2(INLINE_UID_FROM_FUID(MethodFixture::kProcessorUid),
           Steinberg::PClassInfo::kManyInstances, kVstAudioEffectClass,
           MethodFixture::kPluginName, Steinberg::Vst::kDistributable,
           "Instrument|Synth", MethodFixture::kVersion, kVstVersionString,
           MethodFixture::Processor::create)

DEF_CLASS2(INLINE_UID_FROM_FUID(MethodFixture::kControllerUid),
           Steinberg::PClassInfo::kManyInstances, kVstComponentControllerClass,
           "Method Fixture Controller", 0, "", MethodFixture::kVersion,
           kVstVersionString, MethodFixture::Controller::create)

END_FACTORY
