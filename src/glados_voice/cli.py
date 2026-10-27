"""``glados-voice`` command: download models or speak once and report latency."""

import argparse
import sys
import time


def _say(text: str) -> int:
    from .engine import VoiceEngine

    t0 = time.perf_counter()
    engine = VoiceEngine().start()
    engine.ready.wait()
    if engine.error:
        print(f"Load failed: {engine.error!r}")
        return 1
    print(f"Ready in {time.perf_counter() - t0:.2f}s {engine.status()['providers']}")
    for _ in range(2):  # the second run shows the warm latency
        engine.speak(text)
        engine.wait_idle()
        print(f"Time to first audio: {engine.last_first_audio_ms:.0f} ms")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="glados-voice", description="GLaDOS voice tools")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download-models", help="download and verify the ONNX model files")
    say = commands.add_parser("say", help="speak text once and print latency")
    say.add_argument("text", nargs="+")
    args = parser.parse_args(argv)

    if args.command == "download-models":
        from .models import ensure_models

        print(f"Models ready in {ensure_models()}")
        return 0
    return _say(" ".join(args.text))


if __name__ == "__main__":
    sys.exit(main())
