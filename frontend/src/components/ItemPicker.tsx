import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { api, ItemListEntry } from "../api";

// Search box that lets you pick an existing item.
export default function ItemPicker({ onPick, disabled }: { onPick: (item: ItemListEntry) => void; disabled?: boolean }) {
  const [q, setQ] = useState("");
  const results = useQuery({
    queryKey: ["items", "picker", q],
    queryFn: () => api.items({ q, page_size: "8" }),
    enabled: q.trim().length >= 2,
  });
  return (
    <div className="picker">
      <input aria-label="Find an item" placeholder="Find an item by title, year, country…" value={q} onChange={(e) => setQ(e.target.value)} disabled={disabled} />
      {q.trim().length >= 2 && (
        <ul className="picker-results">
          {results.data?.items.length === 0 && <li className="muted">No items match.</li>}
          {results.data?.items.map((it) => (
            <li key={it.id}>
              <button type="button" onClick={() => onPick(it)} disabled={disabled}>
                {it.cover_thumb_url && <img src={it.cover_thumb_url} alt="" />}
                <span>{it.title}</span>
                <span className="hint">#{it.id}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
