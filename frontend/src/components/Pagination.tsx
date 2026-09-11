import { ArrowLeft, ArrowRight } from "lucide-react";

import { Button } from "@/components/Button";

interface PaginationProps {
  page: number;
  onChange: (page: number) => void;
  totalPages?: number;
  hasNext?: boolean;
  hasPrevious?: boolean;
  className?: string;
}

export function Pagination({ page, onChange, totalPages, hasNext, hasPrevious, className = "" }: PaginationProps) {
  const canGoPrevious = hasPrevious ?? page > 1;
  const canGoNext = hasNext ?? (totalPages ? page < totalPages : false);
  if (!canGoPrevious && !canGoNext && (!totalPages || totalPages <= 1)) return null;

  return (
    <nav className={`flex flex-wrap items-center justify-center gap-3 print:hidden ${className}`} aria-label="التنقل بين الصفحات">
      <Button type="button" variant="secondary" disabled={!canGoPrevious} onClick={() => onChange(page - 1)}>
        <ArrowRight aria-hidden size={16} /> السابق
      </Button>
      <span className="min-w-24 text-center text-sm font-bold text-slate-600" aria-current="page">
        صفحة {page}{totalPages ? ` من ${totalPages}` : ""}
      </span>
      <Button type="button" variant="secondary" disabled={!canGoNext} onClick={() => onChange(page + 1)}>
        التالي <ArrowLeft aria-hidden size={16} />
      </Button>
    </nav>
  );
}
