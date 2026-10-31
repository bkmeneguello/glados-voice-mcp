# Third-party notices

This project (`LICENSE`, MIT) builds on the following work. Their licenses are compatible with MIT and are reproduced
here because the installed package contains their code.

## GLaDOS-TTS / GlaDOS (MIT)

- `third_party/GLaDOS-TTS` (git submodule): https://github.com/nimaid/GLaDOS-TTS, adapted from
  https://github.com/dnhkng/GlaDOS. It is installed unmodified as the private package `glados_voice._glados`.

```
MIT License

Copyright (c) 2022 David Ng

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Work adapted inside the upstream `glados` package (MIT)

The upstream `glados` package (installed as `glados_voice._glados`) builds on the following projects. Each is MIT licensed; the permission notice above
applies to them with their own copyright lines:

- DeepPhonemizer (https://github.com/as-ideas/DeepPhonemizer), the basis of `phonemizer.py`.
  Copyright (c) 2021 Axel Springer News Media & Tech GmbH & Co. KG - Ideas Engineering
- Piper (https://github.com/rhasspy/piper), the basis of the VITS inference in `tts.py`.
  Copyright (c) 2022 Michael Hansen

The bundled phoneme dictionary files in `models/*.pkl` appear to derive from the CMU Pronouncing Dictionary
(CMUdict, BSD-style license, Copyright (C) Carnegie Mellon University).

## Voice and phonemizer models

The ONNX models are downloaded at first use from the GlaDOS 0.1 release
(https://github.com/dnhkng/GlaDOS/releases/tag/0.1). They are not stored or redistributed in this repository, and this
project makes no claim over them. The voice model imitates the GLaDOS character and its original voice recordings,
which belong to Valve Corporation; the upstream release states no license for it. It is a fan-made model intended for
personal, non-commercial use only, and this project's MIT license does not extend to it.

## Runtime dependencies

These are installed from PyPI and are not part of this repository, so their licenses apply to you separately:

- `num2words` is LGPL licensed. It is imported as a library, not bundled or modified.
- The optional `cuda` extra installs NVIDIA libraries (`nvidia-cuda-runtime`, `nvidia-cublas`, `nvidia-cudnn-cu13`,
  `nvidia-cufft`, `nvidia-curand`) under NVIDIA's proprietary license terms, which you accept by installing them.
- The remaining dependencies (`mcp`, `numpy`, `onnxruntime`, `sounddevice`, `platformdirs` and their dependencies) are
  under permissive licenses (MIT, BSD, Apache-2.0).

## Trademarks

GLaDOS and Portal are properties of Valve Corporation. This is an unofficial fan project, not affiliated with or
endorsed by Valve.
