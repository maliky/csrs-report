import { ArrowLeft, ArrowRight } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "../../components/ui";
import styles from "./users.module.css";

export type TransferItem = {
  id: number;
  label: string;
  description?: string;
};

export function TransferSelector({
  legend,
  available,
  selected,
  onAdd,
  onRemove,
  disabled = false,
}: {
  legend: string;
  available: TransferItem[];
  selected: TransferItem[];
  onAdd: (ids: number[]) => void;
  onRemove: (ids: number[]) => void;
  disabled?: boolean;
}) {
  const [availableQuery, setAvailableQuery] = useState("");
  const [selectedQuery, setSelectedQuery] = useState("");
  const [availableChoice, setAvailableChoice] = useState<number[]>([]);
  const [selectedChoice, setSelectedChoice] = useState<number[]>([]);
  const filteredAvailable = useMemo(
    () => filterItems(available, availableQuery),
    [available, availableQuery],
  );
  const filteredSelected = useMemo(
    () => filterItems(selected, selectedQuery),
    [selected, selectedQuery],
  );

  return (
    <fieldset className={styles.transferFieldset} disabled={disabled}>
      <legend>{legend}</legend>
      <div className={styles.transferGrid}>
        <TransferPanel
          id={`${slug(legend)}-available`}
          title="Disponibles"
          query={availableQuery}
          onQuery={setAvailableQuery}
          items={filteredAvailable}
          value={availableChoice}
          onChange={setAvailableChoice}
        />
        <div className={styles.transferActions}>
          <Button
            type="button"
            variant="secondary"
            disabled={!availableChoice.length || disabled}
            onClick={() => {
              onAdd(availableChoice);
              setAvailableChoice([]);
            }}
          >
            Ajouter <ArrowRight size={18} aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="quiet"
            disabled={!selectedChoice.length || disabled}
            onClick={() => {
              onRemove(selectedChoice);
              setSelectedChoice([]);
            }}
          >
            <ArrowLeft size={18} aria-hidden="true" /> Retirer
          </Button>
        </div>
        <TransferPanel
          id={`${slug(legend)}-selected`}
          title="Sélectionnés"
          query={selectedQuery}
          onQuery={setSelectedQuery}
          items={filteredSelected}
          value={selectedChoice}
          onChange={setSelectedChoice}
        />
      </div>
    </fieldset>
  );
}

function TransferPanel({
  id,
  title,
  query,
  onQuery,
  items,
  value,
  onChange,
}: {
  id: string;
  title: string;
  query: string;
  onQuery: (query: string) => void;
  items: TransferItem[];
  value: number[];
  onChange: (ids: number[]) => void;
}) {
  return (
    <div className={styles.transferPanel}>
      <label htmlFor={`${id}-search`}>{title}</label>
      <input
        id={`${id}-search`}
        type="search"
        value={query}
        onChange={(event) => onQuery(event.target.value)}
        placeholder="Filtrer la liste"
      />
      <select
        id={id}
        multiple
        value={value.map(String)}
        aria-label={`${title} — ${id}`}
        onChange={(event) =>
          onChange(
            Array.from(event.currentTarget.selectedOptions, (option) =>
              Number(option.value),
            ),
          )
        }
      >
        {items.map((item) => (
          <option key={item.id} value={item.id} title={item.description}>
            {item.label}
            {item.description ? ` — ${item.description}` : ""}
          </option>
        ))}
      </select>
      <small>{items.length} élément(s)</small>
    </div>
  );
}

function filterItems(items: TransferItem[], query: string) {
  const normalized = query.trim().toLocaleLowerCase("fr");
  if (!normalized) return items;
  return items.filter((item) =>
    `${item.label} ${item.description ?? ""}`
      .toLocaleLowerCase("fr")
      .includes(normalized),
  );
}

function slug(value: string) {
  return value.toLocaleLowerCase("fr").replace(/[^a-z0-9]+/g, "-");
}
