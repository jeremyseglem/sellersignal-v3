/**
 * Shared owner_type → human-readable label conversion.
 *
 * Used by ParcelDossier, PlaybookList, and any other UI surface that
 * renders a parcel's owner classification. Keeping this in one place
 * prevents inconsistencies like the dossier showing "Trust" while
 * the playbook shows "TRUST" for the same owner.
 *
 * The backend's _derive_owner_type (backend/ingest/arcgis.py) returns
 * one of these lowercase strings:
 *   individual | trust | llc | estate | gov | nonprofit | unknown
 *
 * Any new backend category MUST be added here. If an unexpected
 * value arrives, the fallback does Title Case on the raw string —
 * readable but obviously not one of the canonical categories.
 */

const OWNER_TYPE_LABELS = {
  individual: 'Individual',
  trust:      'Trust',
  llc:        'LLC',
  estate:     'Estate',
  gov:        'Government',
  nonprofit:  'Nonprofit',
  // Legacy value some older rows may still have — mapped for safety
  company:    'Company',
  // 'unknown' intentionally not included — callers get null and hide
  // the badge rather than showing a useless "Unknown" label.
};

export function ownerTypeLabel(t) {
  if (!t) return null;
  const key = String(t).toLowerCase();
  if (key === 'unknown') return null;
  if (OWNER_TYPE_LABELS[key]) return OWNER_TYPE_LABELS[key];
  // Fallback: Title Case the raw string for any unexpected category
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/**
 * Whether this owner type is a plausible seller target.
 *
 * Governments and nonprofits (churches, YMCA, etc.) are effectively
 * not going to sell residential real estate — the direct-mail
 * playbook ("Dear firstname...") is inappropriate for them. The
 * dossier uses this flag to hide the Six Letters action button and
 * to suppress HIGH EQUITY / MATURE LLC seller-intent tags.
 */
export function isSellerTargetType(t) {
  if (!t) return true; // unknown = default to showing
  const key = String(t).toLowerCase();
  return key !== 'gov' && key !== 'nonprofit';
}
