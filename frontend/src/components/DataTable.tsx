import type { ReactNode } from "react";

export interface Column<T> {
  header: string;
  accessor: keyof T | string;
  render?: (row: T) => ReactNode;
  className?: string;
}

interface DataTableProps<T extends Record<string, unknown>> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string;
  emptyMessage?: string;
  className?: string;
}

function getCellValue<T extends Record<string, unknown>>(
  row: T,
  accessor: string
): ReactNode {
  const value = row[accessor];
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/** Generic dark-themed table with typed column config. */
export default function DataTable<T extends Record<string, unknown>>({
  columns,
  data,
  keyExtractor,
  emptyMessage = "No data available.",
  className = "",
}: DataTableProps<T>) {
  return (
    <div
      className={[
        "overflow-hidden rounded-lg border border-zinc-700",
        className,
      ].join(" ")}
    >
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-sm" role="table">
          <thead>
            <tr className="border-b border-zinc-700 bg-zinc-800/60">
              {columns.map((col) => (
                <th
                  key={col.accessor as string}
                  scope="col"
                  className={[
                    "px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-zinc-400",
                    col.className ?? "",
                  ].join(" ")}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-700/50">
            {data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-4 py-10 text-center text-sm text-zinc-500"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              data.map((row) => (
                <tr
                  key={keyExtractor(row)}
                  className="bg-zinc-800/30 transition-colors hover:bg-zinc-800/70"
                >
                  {columns.map((col) => (
                    <td
                      key={col.accessor as string}
                      className={[
                        "px-4 py-3 text-zinc-200",
                        col.className ?? "",
                      ].join(" ")}
                    >
                      {col.render
                        ? col.render(row)
                        : getCellValue(row, col.accessor as string)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
