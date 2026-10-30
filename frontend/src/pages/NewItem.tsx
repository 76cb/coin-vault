import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "../api";
import ItemForm from "../components/ItemForm";

export default function NewItem() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  return (
    <>
      <div className="page-head">
        <h1>Add item</h1>
      </div>
      <p className="muted lede">Fill in what you know; everything except the title can wait. You can add photos once it's saved.</p>
      <ItemForm
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
