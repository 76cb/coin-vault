// The collection tile: the whole photo, uncropped, on the navy tray. Without a photo, an empty coin well.

export default function Flip({ src, alt, size = "md" }: { src: string | null; alt: string; size?: "sm" | "md" | "lg" }) {
  return (
    <div className={`flip flip-${size}`}>
      <div className={`flip-window${src ? " has-photo" : ""}`}>
        {src ? <img src={src} alt={alt} loading="lazy" /> : <span className="flip-empty">No photo</span>}
      </div>
    </div>
  );
}
