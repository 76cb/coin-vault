import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, Described } from "../api";
import ItemForm, { defaultsFromDescription, FormState } from "../components/ItemForm";
import QuickStart from "../components/QuickStart";

export default function NewItem() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [seed, setSeed] = useState<{ n: number; defaults: Partial<FormState> } | null>(null);
  const use = useCallback((d: Described) => setSeed({ n: Date.now(), defaults: defaultsFromDescription(d) }), []);
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
          await qc.invalidateQueries({ queryKey: ["items"] });
          await qc.invalidateQueries({ queryKey: ["tags"] });
          navigate(`/items/${item.id}`, { replace: true });
        }}
      />
    </>
  );
}
