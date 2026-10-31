import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import ItemForm, { FormState } from "../components/ItemForm";
import QuickStart, { AfterSave } from "../components/QuickStart";

export default function NewItem() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [seed, setSeed] = useState<{ n: number; defaults: Partial<FormState>; after?: AfterSave } | null>(null);
  const use = useCallback((defaults: Partial<FormState>, after?: AfterSave) => setSeed({ n: Date.now(), defaults, after }), []);
  return (
    <>
      <div className="page-head">
        <h1>Add item</h1>
      </div>
      <QuickStart onUse={use} />
      <p className="muted lede">Or fill in the form yourself. Only the title is required; photos can be added once it's saved.</p>
      <ItemForm
        key={seed?.n ?? 0}
        defaults={seed?.defaults}
        submitLabel="Save item"
        onCancel={() => navigate(-1)}
        onSubmit={async (payload) => {
          const item = await api.createItem(payload);
          let note: string | undefined;
          if (seed?.after?.pcgsPriceGuide) {
            try {
              await api.pcgsPriceGuide(item.id);
            } catch (err) {
              note = `Saved, but the PCGS price guide value wasn't: ${(err as Error).message}`;
            }
          }
          await qc.invalidateQueries({ queryKey: ["items"] });
          await qc.invalidateQueries({ queryKey: ["tags"] });
          await qc.invalidateQueries({ queryKey: ["summary"] });
          navigate(`/items/${item.id}`, { replace: true, state: note ? { note } : undefined });
        }}
      />
    </>
  );
}
