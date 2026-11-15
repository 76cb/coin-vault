import { DragEvent, useId, useRef, useState } from "react";

const ACCEPT = "image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif,.heic,.heif";

export default function DropZone({
  onFiles,
  label,
  hint = "Drag files here, or choose them. JPEG, PNG, WebP or HEIC.",
  accept = ACCEPT,
  multiple = true,
  disabled = false,
  camera = accept === ACCEPT,
}: {
  onFiles: (files: File[]) => void;
  label: string;
  hint?: string;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  camera?: boolean; // offer "Take a photo" (photo drop zones only)
}) {
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const id = useId();

  const take = (list: FileList | null) => {
    const files = Array.from(list ?? []);
    if (files.length) onFiles(files);
  };

  return (
    <>
    <div
      className={`dropzone${over ? " over" : ""}${disabled ? " disabled" : ""}`}
      onDragOver={(e: DragEvent) => {
        e.preventDefault();
        if (!disabled) setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e: DragEvent) => {
        e.preventDefault();
        setOver(false);
        if (!disabled) take(e.dataTransfer.files);
      }}
    >
      <label htmlFor={id} className="dropzone-label">
        <strong>{disabled ? "Uploading…" : label}</strong>
        <span className="hint">{hint}</span>
      </label>
      <input
        ref={input}
        id={id}
        type="file"
        accept={accept}
        multiple={multiple}
        disabled={disabled}
        onChange={(e) => {
          take(e.target.files);
          if (input.current) input.current.value = "";
        }}
      />
    </div>
    {camera && (
      /* on a phone this opens the camera, so a photo goes straight in without saving it to the camera roll first */
      <label className={`button ghost small camera-button${disabled ? " disabled" : ""}`}>
        Take a photo
        <input
          type="file"
          accept="image/*"
          capture="environment"
          disabled={disabled}
          className="visually-hidden"
          onChange={(e) => {
            take(e.target.files);
            e.target.value = "";
          }}
        />
      </label>
    )}
    </>
  );
}
