import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { purgeSensitiveBrowserCaches } from "@/app/cacheSafety";
import { Button } from "@/components/Button";
import { ME_QUERY_KEY } from "@/features/auth/useMe";

export function SpaceSwitchButton({
  destination,
  children,
}: {
  destination: string;
  children: string;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  async function switchSpace() {
    setBusy(true);
    try {
      const me = queryClient.getQueryData(ME_QUERY_KEY);
      await queryClient.cancelQueries();
      queryClient.removeQueries({
        predicate: (query) => query.queryKey[0] !== "me",
      });
      queryClient.getMutationCache().clear();
      await purgeSensitiveBrowserCaches();
      queryClient.setQueryData(ME_QUERY_KEY, me);
      navigate(destination);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Button
      variant="secondary"
      className="text-xs sm:text-sm"
      loading={busy}
      onClick={() => void switchSpace()}
    >
      {children}
    </Button>
  );
}
