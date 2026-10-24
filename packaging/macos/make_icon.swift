// Dessine l'icône de l'app (1024×1024) : fond dégradé arrondi et symbole « lecture ».
// Utilisation : swift make_icon.swift sortie.png
import AppKit

let size: CGFloat = 1024
let image = NSImage(size: NSSize(width: size, height: size))
image.lockFocus()
let inset: CGFloat = 100
let rect = NSRect(x: inset, y: inset, width: size - 2 * inset, height: size - 2 * inset)
let shape = NSBezierPath(roundedRect: rect, xRadius: 185, yRadius: 185)
NSGradient(starting: NSColor(calibratedRed: 0.20, green: 0.55, blue: 1.0, alpha: 1),
           ending: NSColor(calibratedRed: 0.42, green: 0.22, blue: 0.85, alpha: 1))!.draw(in: shape, angle: -60)

// Bandes de pellicule
NSColor(white: 1, alpha: 0.22).setFill()
for i in 0..<6 {
    let x = rect.minX + 70 + CGFloat(i) * 120
    NSBezierPath(roundedRect: NSRect(x: x, y: rect.maxY - 110, width: 70, height: 50), xRadius: 12, yRadius: 12).fill()
    NSBezierPath(roundedRect: NSRect(x: x, y: rect.minY + 60, width: 70, height: 50), xRadius: 12, yRadius: 12).fill()
}

// Triangle de lecture
let play = NSBezierPath()
play.move(to: NSPoint(x: 410, y: 330))
play.line(to: NSPoint(x: 410, y: 694))
play.line(to: NSPoint(x: 700, y: 512))
play.close()
NSColor.white.setFill()
play.fill()
image.unlockFocus()

let rep = NSBitmapImageRep(data: image.tiffRepresentation!)!
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
