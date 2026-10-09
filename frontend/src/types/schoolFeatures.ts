export type SchoolFeature = "ABSENCE_SMS" | "PARENT_PORTAL" | "BIOMETRIC_DEVICES";
export type SchoolFeatures = Record<SchoolFeature, boolean>;
export interface SchoolFeatureState { school_id: number; features: SchoolFeatures }
