import ArgumentParser
import FluidAudio
import Foundation

/// Transcribe an audio file with FluidAudio (Parakeet TDT v2, CoreML) and
/// print JSON with word-level timestamps:
///   {"text": "...", "duration": 12.3,
///    "words": [{"word": "the", "start": 0.12, "end": 0.30}, ...]}
///
/// Bridge pattern borrowed from anvanvan/mac-whisper-speedtest.
@main
struct FluidAudioBridge: AsyncParsableCommand {
    static let configuration = CommandConfiguration(
        commandName: "fluidaudio-bridge",
        abstract: "Transcribe audio with word timestamps for Python consumption",
        version: "2.0.0"
    )

    @Argument(help: "Path to the input audio file (any AVFoundation-readable format)")
    var inputFile: String

    func run() async throws {
        guard FileManager.default.fileExists(atPath: inputFile) else {
            FileHandle.standardError.write(Data("Error: no such file: \(inputFile)\n".utf8))
            throw ExitCode.failure
        }

        // v2 = English-only Parakeet, higher recall on English narration.
        let models = try await AsrModels.downloadAndLoad(version: .v2)
        let asrManager = AsrManager(config: .default)
        try await asrManager.loadModels(models)

        var decoderState = TdtDecoderState.make()
        let result = try await asrManager.transcribe(
            URL(fileURLWithPath: inputFile), decoderState: &decoderState)

        let words = buildWordTimings(from: result.tokenTimings ?? [])
        let output: [String: Any] = [
            "text": result.text,
            "duration": result.duration,
            "words": words.map {
                ["word": $0.word, "start": $0.startTime, "end": $0.endTime]
            },
        ]
        let jsonData = try JSONSerialization.data(withJSONObject: output)
        FileHandle.standardOutput.write(jsonData)
        FileHandle.standardOutput.write(Data("\n".utf8))
    }
}
