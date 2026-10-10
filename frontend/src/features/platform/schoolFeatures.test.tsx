import { QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { queryClient } from "@/app/queryClient";
import { type SchoolDetail } from "@/features/platform/api";
import { SchoolFeaturesPanel } from "@/features/platform/SchoolFeaturesPanel";
import { featureForPath, type SchoolFeatures } from "@/features/platform/schoolFeatures";
import { buildMe, membership, mockApi } from "@/test/mockApi";
import { renderApp } from "@/test/renderApp";

const school = { id: 42, name: "مدرسة الاختبار", slug: "school-features" };
const disabled: SchoolFeatures = { ABSENCE_SMS: false, PARENT_PORTAL: false, BIOMETRIC_DEVICES: false };
const manager = buildMe({ active_school: school, roles: ["SCHOOL_MANAGER"], memberships: [membership(1, school.id, school.name, ["SCHOOL_MANAGER"])], school_features: disabled });

function Panel({ canManage = true }: { canManage?: boolean }) {
  const detail = useQuery<SchoolDetail>({ queryKey: ["platform", "school", school.id], queryFn: async () => { throw new Error("Unexpected detail fetch"); }, enabled: false });
  return detail.data ? <SchoolFeaturesPanel detail={detail.data} canManage={canManage} /> : null;
}

function renderPanel(canManage = true) {
  // The panel reads only school id and feature flags; the rest belongs to its parent page.
  queryClient.setQueryData(["platform", "school", school.id], { id: school.id, feature_access: disabled });
  return render(<QueryClientProvider client={queryClient}><Panel canManage={canManage} /></QueryClientProvider>);
}

describe("school feature controls", () => {
  beforeEach(() => { queryClient.clear(); document.cookie = "csrftoken=test-token"; });

  it("saves exactly one flag and renders the confirmed server state", async () => {
    const { calls } = mockApi({ "/features/": { body: { school_id: school.id, features: { ...disabled, PARENT_PORTAL: true } } } });
    renderPanel();
    await userEvent.click(screen.getByRole("switch", { name: "تفعيل بوابة ولي الأمر" }));
    await waitFor(() => expect(screen.getByRole("switch", { name: "تفعيل بوابة ولي الأمر" })).toHaveAttribute("aria-checked", "true"));
    expect(calls).toHaveLength(1);
    expect(calls[0]?.url).toContain(`/platform/schools/${school.id}/features/`);
    expect(JSON.parse(String(calls[0]?.init?.body))).toEqual({ feature: "PARENT_PORTAL", enabled: true });
    expect(screen.getByRole("switch", { name: "تفعيل رسائل الغياب" })).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("switch", { name: "تفعيل الربط مع أجهزة البصمة" })).toHaveAttribute("aria-checked", "false");
    expect(await screen.findByText("تم حفظ حالة الميزة")).toBeInTheDocument();
  });

  it("keeps the confirmed flag after a failed save", async () => {
    mockApi({ "/features/": { status: 403, body: { code: "PERMISSION_DENIED", message: "لا تملك صلاحية التعديل", details: {} } } });
    renderPanel();
    await userEvent.click(screen.getByRole("switch", { name: "تفعيل رسائل الغياب" }));
    expect(await screen.findByText("لا تملك صلاحية التعديل")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "تفعيل رسائل الغياب" })).toHaveAttribute("aria-checked", "false");
    expect(screen.queryByText("تم حفظ حالة الميزة")).not.toBeInTheDocument();
  });

  it("prevents changes by read-only platform staff", async () => {
    const { calls } = mockApi({});
    renderPanel(false);
    for (const control of screen.getAllByRole("switch")) expect(control).toBeDisabled();
    await userEvent.click(screen.getByRole("switch", { name: "تفعيل بوابة ولي الأمر" }));
    expect(calls).toHaveLength(0);
  });

  it.each([
    ["/parent-management", "بوابة ولي الأمر", "/staff/parents/"],
    ["/parent-management/", "بوابة ولي الأمر", "/staff/parents/"],
    ["/attendance/absence-messages", "رسائل الغياب", "/school/sms/"],
    ["/devices", "الربط مع أجهزة البصمة", "/devices/"],
    ["/settings?section=parents", "بوابة ولي الأمر", "/staff/parents/"],
    ["/settings?section=sms", "رسائل الغياب", "/school/sms/"],
  ])("blocks direct route %s without calling its protected APIs", async (path, label, api) => {
    const { calls } = mockApi({ "/auth/me/": { body: manager }, "/school/features/": { body: { school_id: school.id, features: disabled } } });
    renderApp(path);
    expect(await screen.findByRole("region", { name: `${label} تتطلب اشتراكًا` })).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes(api))).toBe(false);
  });

  it("keeps the icon visible and opens a subscription notice without navigating", async () => {
    mockApi({ "/auth/me/": { body: manager }, "/school/features/": { body: { school_id: school.id, features: disabled } } });
    renderApp("/workspace");
    const navigation = await screen.findByRole("navigation", { name: "التنقل الرئيسي" });
    const locked = within(navigation).getByRole("button", { name: "إدارة أولياء الأمور — يلزم اشتراك" });
    expect(locked).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(locked);
    expect(await screen.findByRole("dialog", { name: "ميزة تتطلب اشتراكًا" })).toBeInTheDocument();
    expect(within(navigation).queryByRole("link", { name: "إدارة أولياء الأمور" })).not.toBeInTheDocument();
  });

  it("re-enables navigation after refreshing the same school's feature state", async () => {
    let flags = disabled;
    mockApi({ "/auth/me/": { body: manager }, "/school/features/": () => ({ body: { school_id: school.id, features: flags } }) });
    renderApp("/workspace");
    expect(await screen.findByRole("button", { name: "إدارة أولياء الأمور — يلزم اشتراك" })).toBeInTheDocument();
    flags = { ...disabled, PARENT_PORTAL: true };
    await act(async () => { await queryClient.invalidateQueries({ queryKey: ["school", school.id, "feature-access"] }); });
    expect(await screen.findByRole("link", { name: "إدارة أولياء الأمور" })).toHaveAttribute("href", "/parent-management");
  });

  it("ignores feature state belonging to a different school", async () => {
    mockApi({ "/auth/me/": { body: manager }, "/school/features/": { body: { school_id: 999, features: { ...disabled, PARENT_PORTAL: true } } } });
    renderApp("/parent-management");
    expect(await screen.findByRole("region", { name: "بوابة ولي الأمر تتطلب اشتراكًا" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "إدارة أولياء الأمور" })).not.toBeInTheDocument();
  });

  it("does not gate manual morning attendance", () => {
    expect(featureForPath("/morning")).toBeNull();
    expect(featureForPath("/settings", "?section=attendance")).toBeNull();
  });
});
