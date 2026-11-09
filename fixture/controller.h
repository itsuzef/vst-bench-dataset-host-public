// SPDX-FileCopyrightText: 2026 Youssef Hemimy
// SPDX-License-Identifier: MIT

#pragma once

#include "public.sdk/source/vst/vsteditcontroller.h"

namespace MethodFixture {

class Controller final : public Steinberg::Vst::EditController {
public:
  static Steinberg::FUnknown *create(void *);

  Steinberg::tresult PLUGIN_API
  initialize(Steinberg::FUnknown *context) override;
};

} // namespace MethodFixture
