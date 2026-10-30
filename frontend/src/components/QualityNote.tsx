import { Link } from "react-router-dom";

import { Quality } from "../api";

export function QualityNote({ quality }: { quality: Quality }) {
  if (!quality?.issues?.length) return null;
  return (
    <ul className="quality-note">
      {quality.issues.map((i) => (
        <li key={i.check}>{i.advice}</li>
      ))}
    </ul>
  );
}

export function DuplicateNote({ kind, itemId }: { kind?: string | null; itemId?: number | null }) {
  if (!kind) return null;
  return (
    <p className="dup-note">
      {kind === "exact" ? "Same file as a photo on " : "Looks like a photo on "}
      {itemId ? <Link to={`/items/${itemId}`}>item #{itemId}</Link> : "another item"}
    </p>
  );
}
