// PNG 帧序列 → H.264 MP4。macOS 自带的 AVFoundation，**不需要 ffmpeg**。
//
// 为什么不用 ffmpeg：装它要动整台机器（brew install ffmpeg 会拖一堆依赖），而这个
// skill 一直在守「不加新依赖」—— Chrome 是系统里就有的，PIL 也是现成的，编码这块
// AVFoundation 同样是系统里就有的。三条腿都落地，导出链路就没有外部前提。
//
// 用法：  enc <out.mp4> <fps> <帧清单文件>
//         帧清单文件是每行一个 PNG 路径（不走命令行参数：几百个路径会顶到 ARG_MAX）
//
// 编译：  swiftc -O h264_encode.swift -o <缓存目录>/deck-h264
//         （animate.py 负责编译并按源码 mtime 缓存，不在每次导出时重编）
import AVFoundation
import CoreGraphics
import Foundation
import ImageIO
import VideoToolbox

func die(_ msg: String) -> Never {
    FileHandle.standardError.write("✗ \(msg)\n".data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 4 else { die("用法: enc <out.mp4> <fps> <帧清单文件>") }
let outPath = args[1]
guard let fps = Int32(args[2]), fps > 0 else { die("fps 必须是正整数，收到 \(args[2])") }
let listPath = args[3]

guard let listText = try? String(contentsOfFile: listPath, encoding: .utf8) else {
    die("读不到帧清单：\(listPath)")
}
let frames = listText.split(separator: "\n").map(String.init).filter { !$0.isEmpty }
guard !frames.isEmpty else { die("帧清单是空的：\(listPath)") }

// 尺寸取第一帧；H.264 要求宽高都是偶数（奇数维度会被编码器拒绝或悄悄裁一列）
guard let src0 = CGImageSourceCreateWithURL(URL(fileURLWithPath: frames[0]) as CFURL, nil),
      let img0 = CGImageSourceCreateImageAtIndex(src0, 0, nil) else {
    die("读不出第一帧：\(frames[0])")
}
let w = img0.width, h = img0.height
if w % 2 != 0 || h % 2 != 0 {
    die("帧尺寸必须是偶数（H.264 要求），实际 \(w)x\(h)")
}

let outURL = URL(fileURLWithPath: outPath)
try? FileManager.default.removeItem(at: outURL)
guard let writer = try? AVAssetWriter(outputURL: outURL, fileType: .mp4) else {
    die("建不了 AVAssetWriter（输出路径可写吗？）")
}

let settings: [String: Any] = [
    AVVideoCodecKey: AVVideoCodecType.h264,
    AVVideoWidthKey: w,
    AVVideoHeightKey: h,
    AVVideoCompressionPropertiesKey: [
        AVVideoAverageBitRateKey: max(6_000_000, w * h * 4),   // 按分辨率给码率
        AVVideoMaxKeyFrameIntervalKey: fps,                      // 每秒钟一个关键帧，seek 干净
        AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
    ],
]

let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
let adaptor = AVAssetWriterInputPixelBufferAdaptor(
    assetWriterInput: input,
    sourcePixelBufferAttributes: [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
        kCVPixelBufferWidthKey as String: w,
        kCVPixelBufferHeightKey as String: h,
    ])
guard writer.canAdd(input) else { die("writer 不接受这个 video input") }
writer.add(input)
guard writer.startWriting() else { die("startWriting 失败：\(String(describing: writer.error))") }
writer.startSession(atSourceTime: .zero)

let cs = CGColorSpaceCreateDeviceRGB()
for (i, path) in frames.enumerated() {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil),
          let img = CGImageSourceCreateImageAtIndex(src, 0, nil) else {
        die("读不出第 \(i) 帧：\(path)")
    }
    if img.width != w || img.height != h {
        die("第 \(i) 帧尺寸是 \(img.width)x\(img.height)，与第一帧 \(w)x\(h) 不一致")
    }
    var pb: CVPixelBuffer?
    CVPixelBufferCreate(kCFAllocatorDefault, w, h, kCVPixelFormatType_32ARGB,
                        [kCVPixelBufferCGImageCompatibilityKey: true] as CFDictionary, &pb)
    guard let buf = pb else { die("第 \(i) 帧建不了 pixel buffer") }
    CVPixelBufferLockBaseAddress(buf, [])
    guard let ctx = CGContext(data: CVPixelBufferGetBaseAddress(buf), width: w, height: h,
                              bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(buf),
                              space: cs,
                              bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue) else {
        die("第 \(i) 帧建不了 CGContext")
    }
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    CVPixelBufferUnlockBaseAddress(buf, [])

    // 背压：input 没准备好就等 —— 不等会把帧丢掉，而且**不报错**（视频悄悄变短）
    while !input.isReadyForMoreMediaData { usleep(2000) }
    let pts = CMTime(value: CMTimeValue(i), timescale: fps)
    if !adaptor.append(buf, withPresentationTime: pts) {
        die("第 \(i) 帧 append 失败：\(String(describing: writer.error))")
    }
}

input.markAsFinished()
let sem = DispatchSemaphore(value: 0)
writer.finishWriting { sem.signal() }
sem.wait()
guard writer.status == .completed else {
    die("写完了但状态是 \(writer.status.rawValue)：\(String(describing: writer.error))")
}
print("OK \(w)x\(h) \(frames.count) 帧 @ \(fps)fps")
