import { ChevronDown } from "lucide-react";
import type { ModelId, ModelOption } from "../types";

interface ModelSelectorProps {
  models: ModelOption[];
  selectedModel: ModelId;
  disabled: boolean;
  onSelect: (model: ModelId) => void;
}

export function ModelSelector({ models, selectedModel, disabled, onSelect }: ModelSelectorProps) {
  return (
    <div className="model-selector">
      <label className="sr-only" htmlFor="generation-model">Chọn mô hình AI</label>
      <select
        disabled={disabled}
        id="generation-model"
        onChange={(event) => onSelect(event.target.value as ModelId)}
        value={selectedModel}
      >
        {models.map((model) => (
          <option disabled={!model.configured} key={model.id} value={model.id}>
            {model.label}{model.configured ? "" : " · Chưa cấu hình"}
          </option>
        ))}
      </select>
      <ChevronDown aria-hidden="true" size={14} />
    </div>
  );
}
