// A coin "2x2 flip": the circular photo window in a square card-stock holder.

export default function Flip({ src, alt, size = "md" }: { src: string | null; alt: string; size?: "sm" | "md" | "lg" }) {
  return (
    <div className={`flip flip-${size}`}>
      <div className="flip-window">
        {src ? <img src={src} alt={alt} loading="lazy" /> : <span className="flip-empty">No photo</span>}
      </div>
    </div>
  );
}
