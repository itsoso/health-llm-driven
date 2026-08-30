"""Dormant, non-authorizing signing for the Health Day Phase 1a shadow.

This module deliberately has no production key source or runtime wiring.  It
accepts an injected key provider, signs exact immutable DTO projections, and
returns only test-harness artifacts.  The serializer implements the restricted
JCS-compatible subset documented by the Phase 1a contract; it is not a general
RFC 8785 implementation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.services import health_day_shadow_contracts as contracts
from app.services.health_day_shadow_contracts import (
    _SIGNED_SHADOW_ITEM_KEY_BINDER,
)


HEALTH_DAY_SHADOW_DOMAIN = b"health-day-shadow-v1"
_HKDF_SALT = HEALTH_DAY_SHADOW_DOMAIN + b"\x00hkdf-salt-v1"
_PURPOSES = frozenset({"source-payload", "manifest-digest", "item-key"})
_KEY_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,32}")
_CONTROLLED_ASCII_RE = re.compile(r"[A-Za-z0-9_.:-]+")
_JCS_KEY_RE = re.compile(r"[A-Za-z0-9_.:-]+")
_CANONICAL_DECIMAL_RE = re.compile(
    r"(?:0|-?[1-9][0-9]*|-?(?:0|[1-9][0-9]*)\.[0-9]*[1-9])"
)
_IJSON_SAFE_INTEGER = 2**53 - 1
_JCS_MAX_NESTING_DEPTH = 64
_SOURCE_ORDER_INDEX = {
    source_kind: index
    for index, source_kind in enumerate(contracts.HEALTH_DAY_SOURCE_ORDER_V1)
}


class ShadowSigningError(ValueError):
    """Controlled signing failure whose message never contains input values."""

    __slots__ = ()


class ShadowKeyProvider(Protocol):
    """Injected key capability; Phase 1a deliberately has no default provider."""

    def read_key(self) -> tuple[str, bytes]: ...


@dataclass(frozen=True, slots=True)
class SourceSigningInput:
    source_kind: contracts.HealthDaySourceKind
    source_role: contracts.HealthDaySourceRole
    revision: str | None
    acquired_at: datetime | None
    cutoff: datetime | None
    freshness: contracts.SourceFreshness
    availability: contracts.SourceAvailability
    error_code: contracts.ShadowReasonCode | None
    tombstone_state: contracts.TombstoneState
    value: contracts.SourcePayloadValue = field(repr=False)

    def __post_init__(self) -> None:
        _validate_source_signing_input(self)


@dataclass(frozen=True, slots=True)
class ManifestSigningInput:
    schema_version: str
    owner_id: str
    local_day: date
    timezone: str
    as_of: datetime
    transaction: contracts.HealthDayTransaction
    sources: tuple[SourceSigningInput, ...]

    def __post_init__(self) -> None:
        _validate_manifest_signing_input(self)


@dataclass(frozen=True, slots=True)
class ShadowManifestIdentity:
    schema_version: str
    owner_id: str
    local_day: date

    def __post_init__(self) -> None:
        _require_schema_version(self.schema_version, "manifest_identity")
        _require_owner_id(self.owner_id, "manifest_identity.owner_id")
        _require_exact_date(self.local_day, "manifest_identity.local_day")


def _raise(code: str) -> None:
    raise ShadowSigningError(code) from None


def _revalidate_frozen_contract(
    value: object,
    code: str = "shadow_contract_revalidation_failed",
) -> None:
    try:
        type(value).__post_init__(value)
    except Exception:
        _raise(code)


def _require_exact_type(value: object, expected: type, code: str) -> None:
    if type(value) is not expected:
        _raise(code)


def _require_enum(value: object, expected: type, code: str) -> str:
    if type(value) is not expected:
        _raise(code)
    return value.value  # type: ignore[union-attr]


def _require_bool(value: object, code: str) -> bool:
    _require_exact_type(value, bool, code)
    return value  # type: ignore[return-value]


def _require_int(value: object, code: str) -> int:
    _require_exact_type(value, int, code)
    if not -_IJSON_SAFE_INTEGER <= value <= _IJSON_SAFE_INTEGER:  # type: ignore[operator]
        _raise(code)
    return value  # type: ignore[return-value]


def _require_non_negative_int(value: object, code: str) -> int:
    result = _require_int(value, code)
    if result < 0:
        _raise(code)
    return result


def _require_optional_int(value: object, code: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, code)


def _require_local_minute(value: object, code: str) -> int | None:
    result = _require_optional_int(value, code)
    if result is not None and not 0 <= result <= 1439:
        _raise(code)
    return result


def _require_string(value: object, code: str) -> str:
    _require_exact_type(value, str, code)
    _validate_unicode(value, code)  # type: ignore[arg-type]
    return value  # type: ignore[return-value]


def _require_optional_string(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, code)


def _require_identifier(value: object, code: str) -> str:
    result = _require_string(value, code)
    if not result.isascii() or _CONTROLLED_ASCII_RE.fullmatch(result) is None:
        _raise("source_identifier_invalid")
    return result


def _require_optional_identifier(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _require_identifier(value, code)


def _require_decimal_string(value: object, code: str) -> str:
    result = _require_string(value, code)
    if _CANONICAL_DECIMAL_RE.fullmatch(result) is None:
        _raise("source_decimal_not_canonical")
    return result


def _require_optional_decimal_string(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _require_decimal_string(value, code)


def _require_exact_date(value: object, code: str) -> date:
    _require_exact_type(value, date, code)
    return value  # type: ignore[return-value]


def _require_optional_date(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _require_exact_date(value, code).isoformat()


def _require_utc_datetime(value: object, code: str) -> datetime:
    _require_exact_type(value, datetime, code)
    candidate = value  # type: ignore[assignment]
    try:
        offset = candidate.utcoffset()
    except Exception:
        _raise(code)
    if candidate.tzinfo is None or offset is None:
        _raise(code)
    if offset != timedelta(0):
        _raise(code)
    return candidate


def _timestamp(value: object, code: str) -> str:
    candidate = _require_utc_datetime(value, code)
    return (
        f"{candidate.year:04d}-{candidate.month:02d}-{candidate.day:02d}T"
        f"{candidate.hour:02d}:{candidate.minute:02d}:{candidate.second:02d}."
        f"{candidate.microsecond:06d}Z"
    )


def _optional_timestamp(value: object, code: str) -> str | None:
    if value is None:
        return None
    return _timestamp(value, code)


def _require_schema_version(value: object, code: str) -> str:
    result = _require_string(value, code)
    if result != contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION:
        _raise("shadow_schema_version_unsupported")
    return result


def _require_owner_id(value: object, code: str) -> str:
    result = _require_string(value, code)
    if (
        not result.isascii()
        or not result.isdigit()
        or not any(character != "0" for character in result)
    ):
        _raise("shadow_owner_id_invalid")
    return result


def _require_bundle_owner_id(value: object, code: str) -> str:
    result = _require_owner_id(value, code)
    try:
        int(result)
    except (ValueError, OverflowError, MemoryError):
        _raise("shadow_owner_id_invalid")
    return result


def _require_timezone(value: object, code: str) -> str:
    result = _require_string(value, code)
    try:
        ZoneInfo(result)
    except Exception:
        _raise("shadow_timezone_invalid")
    return result


def _require_manifest_local_day_match(
    as_of: datetime,
    timezone_name: str,
    local_day: date,
) -> None:
    try:
        projected_local_day = as_of.astimezone(ZoneInfo(timezone_name)).date()
    except Exception:
        _raise("manifest_local_day_conversion_failed")
    if projected_local_day != local_day:
        _raise("manifest_local_day_mismatch")


def _validate_unicode(value: str, code: str) -> None:
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _raise(code)


def _reason_codes(value: object, code: str) -> list[str]:
    if type(value) is not tuple:
        _raise(code)
    projected: list[str] = []
    for reason in value:
        projected.append(_require_enum(reason, contracts.ShadowReasonCode, code))
    return projected


def _validate_jcs_subset(
    value: object,
    *,
    depth: int = 0,
    active_containers: set[int] | None = None,
) -> None:
    if depth > _JCS_MAX_NESTING_DEPTH:
        _raise("jcs_nesting_too_deep")
    value_type = type(value)
    if value is None or value_type is bool:
        return
    if value_type is int:
        if not -_IJSON_SAFE_INTEGER <= value <= _IJSON_SAFE_INTEGER:  # type: ignore[operator]
            _raise("jcs_integer_out_of_range")
        return
    if value_type is str:
        _validate_unicode(value, "jcs_unicode_surrogate_invalid")  # type: ignore[arg-type]
        return
    if value_type in {list, tuple}:
        if active_containers is None:
            active_containers = set()
        container_id = id(value)
        if container_id in active_containers:
            _raise("jcs_cycle_detected")
        active_containers.add(container_id)
        try:
            for member in value:  # type: ignore[union-attr]
                _validate_jcs_subset(
                    member,
                    depth=depth + 1,
                    active_containers=active_containers,
                )
        finally:
            active_containers.remove(container_id)
        return
    if value_type is dict:
        if active_containers is None:
            active_containers = set()
        container_id = id(value)
        if container_id in active_containers:
            _raise("jcs_cycle_detected")
        active_containers.add(container_id)
        try:
            for key, member in value.items():  # type: ignore[union-attr]
                if type(key) is not str:
                    _raise("jcs_object_key_type_invalid")
                _validate_unicode(key, "jcs_unicode_surrogate_invalid")
                if not key.isascii() or _JCS_KEY_RE.fullmatch(key) is None:
                    _raise("jcs_object_key_invalid")
                _validate_jcs_subset(
                    member,
                    depth=depth + 1,
                    active_containers=active_containers,
                )
        finally:
            active_containers.remove(container_id)
        return
    if value_type is float:
        _raise("jcs_float_forbidden")
    if value_type is datetime:
        _raise("jcs_datetime_forbidden")
    _raise("jcs_type_forbidden")


def canonical_shadow_jcs_subset_bytes(value: object) -> bytes:
    """Return canonical bytes for the deliberately restricted JCS subset."""

    _validate_jcs_subset(value)
    try:
        return json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeEncodeError):
        _raise("jcs_serialization_failed")


def _validate_key_id(value: object) -> str:
    if type(value) is not str or _KEY_ID_RE.fullmatch(value) is None:
        _raise("shadow_key_id_invalid")
    return value


def _validate_root_key(value: object) -> bytes:
    if type(value) is not bytes or len(value) < 32:
        _raise("shadow_root_key_invalid")
    return value


def _read_key(key_provider: ShadowKeyProvider) -> tuple[str, bytes]:
    if key_provider is None:
        _raise("shadow_key_provider_missing")
    try:
        reader = getattr(key_provider, "read_key", None)
    except Exception:
        _raise("shadow_key_provider_read_failed")
    if not callable(reader):
        _raise("shadow_key_provider_invalid")
    try:
        material = reader()
    except Exception:
        _raise("shadow_key_provider_read_failed")
    if type(material) is not tuple or len(material) != 2:
        _raise("shadow_key_provider_result_invalid")
    key_id, root_key = material
    return _validate_key_id(key_id), _validate_root_key(root_key)


def _require_purpose(purpose: object) -> str:
    if type(purpose) is not str or purpose not in _PURPOSES:
        _raise("shadow_purpose_invalid")
    return purpose


def _derive_purpose_key(root_key: bytes, purpose: str) -> bytes:
    validated_root_key = _validate_root_key(root_key)
    validated_purpose = _require_purpose(purpose)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=(
            HEALTH_DAY_SHADOW_DOMAIN
            + b"\x00"
            + validated_purpose.encode("ascii", "strict")
        ),
    ).derive(validated_root_key)


def _canonical_signing_envelope_bytes(
    payload: object,
    *,
    purpose: str,
    key_id: str,
) -> bytes:
    validated_purpose = _require_purpose(purpose)
    validated_key_id = _validate_key_id(key_id)
    return canonical_shadow_jcs_subset_bytes(
        {
            "key_id": validated_key_id,
            "payload": payload,
            "purpose": validated_purpose,
            "schema_version": contracts.HEALTH_DAY_SHADOW_SCHEMA_VERSION,
        }
    )


def _frame_shadow_envelope(canonical_envelope: bytes) -> bytes:
    if type(canonical_envelope) is not bytes:
        _raise("shadow_envelope_bytes_required")
    if len(canonical_envelope) > 0xFFFFFFFF:
        _raise("shadow_envelope_too_large")
    return (
        len(HEALTH_DAY_SHADOW_DOMAIN).to_bytes(4, "big")
        + HEALTH_DAY_SHADOW_DOMAIN
        + len(canonical_envelope).to_bytes(4, "big")
        + canonical_envelope
    )


def _sign_projected_payload(
    payload: object,
    *,
    purpose: str,
    key_id: str,
    root_key: bytes,
) -> str:
    canonical_envelope = _canonical_signing_envelope_bytes(
        payload,
        purpose=purpose,
        key_id=key_id,
    )
    frame = _frame_shadow_envelope(canonical_envelope)
    derived_key = _derive_purpose_key(root_key, purpose)
    mac_hex = hmac.new(derived_key, frame, hashlib.sha256).hexdigest()
    return f"{_validate_key_id(key_id)}.{mac_hex}"


def _validate_source_signing_input(source_input: SourceSigningInput) -> None:
    if type(source_input) is not SourceSigningInput:
        _raise("source_signing_input_type_invalid")
    _project_source_signing_input(source_input)


def _validate_manifest_signing_input(manifest_input: ManifestSigningInput) -> None:
    if type(manifest_input) is not ManifestSigningInput:
        _raise("manifest_signing_input_type_invalid")
    _require_schema_version(manifest_input.schema_version, "manifest.schema_version")
    _require_bundle_owner_id(manifest_input.owner_id, "manifest.owner_id")
    local_day = _require_exact_date(manifest_input.local_day, "manifest.local_day")
    timezone_name = _require_timezone(manifest_input.timezone, "manifest.timezone")
    as_of = _require_utc_datetime(manifest_input.as_of, "manifest.as_of")
    _require_manifest_local_day_match(as_of, timezone_name, local_day)
    if type(manifest_input.transaction) is not contracts.HealthDayTransaction:
        _raise("manifest_transaction_type_invalid")
    _project_transaction(manifest_input.transaction)
    if type(manifest_input.sources) is not tuple:
        _raise("manifest_sources_tuple_required")
    if not all(type(source) is SourceSigningInput for source in manifest_input.sources):
        _raise("manifest_source_input_type_invalid")
    kinds = tuple(source.source_kind for source in manifest_input.sources)
    if len(kinds) != len(set(kinds)):
        _raise("signing_sources_duplicate_kind")
    try:
        expected = tuple(sorted(kinds, key=_SOURCE_ORDER_INDEX.__getitem__))
    except KeyError:
        _raise("signing_source_kind_invalid")
    if kinds != expected:
        _raise("signing_sources_out_of_order")
    for source in manifest_input.sources:
        _project_source_signing_input(source)


def sign_shadow_source_payload(
    source_input: SourceSigningInput,
    key_provider: ShadowKeyProvider,
) -> str:
    try:
        payload = _project_source_signing_input(source_input)
    except ShadowSigningError:
        raise
    except Exception:
        _raise("source_signing_input_invalid")
    key_id, root_key = _read_key(key_provider)
    return _sign_projected_payload(
        payload,
        purpose="source-payload",
        key_id=key_id,
        root_key=root_key,
    )


def _sign_source_with_key(
    source_input: SourceSigningInput,
    *,
    key_id: str,
    root_key: bytes,
) -> str:
    return _sign_projected_payload(
        _project_source_signing_input(source_input),
        purpose="source-payload",
        key_id=key_id,
        root_key=root_key,
    )


def sign_shadow_manifest(
    manifest: contracts.HealthDayShadowManifest,
    key_provider: ShadowKeyProvider,
) -> str:
    try:
        payload = _project_manifest(manifest)
    except ShadowSigningError:
        raise
    except Exception:
        _raise("shadow_manifest_invalid")
    key_id, root_key = _read_key(key_provider)
    return _sign_projected_payload(
        payload,
        purpose="manifest-digest",
        key_id=key_id,
        root_key=root_key,
    )


def _sign_manifest_with_key(
    manifest: contracts.HealthDayShadowManifest,
    *,
    key_id: str,
    root_key: bytes,
) -> str:
    return _sign_projected_payload(
        _project_manifest(manifest),
        purpose="manifest-digest",
        key_id=key_id,
        root_key=root_key,
    )


def sign_shadow_item_identity(
    manifest_identity: ShadowManifestIdentity,
    item_identity: contracts.ShadowItemIdentity,
    key_provider: ShadowKeyProvider,
) -> str:
    payload = _project_item_identity(manifest_identity, item_identity)
    key_id, root_key = _read_key(key_provider)
    return _sign_projected_payload(
        payload,
        purpose="item-key",
        key_id=key_id,
        root_key=root_key,
    )


def bind_signed_shadow_item_key(
    unsigned_item: contracts.HealthDayShadowItem,
    *,
    manifest_identity: ShadowManifestIdentity,
    key_provider: ShadowKeyProvider,
) -> contracts.HealthDayShadowItem:
    if type(unsigned_item) is not contracts.HealthDayShadowItem:
        _raise("unsigned_shadow_item_type_invalid")
    for item_contract in (
        unsigned_item,
        unsigned_item.identity,
        unsigned_item.timing,
        unsigned_item.safety,
        unsigned_item.ordering_facts,
    ):
        _revalidate_frozen_contract(
            item_contract,
            "unsigned_shadow_item_invalid",
        )
    token = sign_shadow_item_identity(
        manifest_identity,
        unsigned_item.identity,
        key_provider,
    )
    try:
        return _SIGNED_SHADOW_ITEM_KEY_BINDER.bind(unsigned_item, token)
    except (TypeError, ValueError):
        _raise("signed_shadow_item_binding_failed")


def build_digest_bound_shadow_bundle(
    manifest_input: ManifestSigningInput,
    key_provider: ShadowKeyProvider,
) -> contracts.HealthDayShadowBundle:
    if type(manifest_input) is not ManifestSigningInput:
        _raise("manifest_signing_input_type_invalid")
    _validate_manifest_signing_input(manifest_input)
    key_id, root_key = _read_key(key_provider)

    source_results: list[contracts.HealthDaySourceResult] = []
    source_payload_values: list[
        tuple[contracts.HealthDaySourceKind, contracts.SourcePayloadValue]
    ] = []
    for source_input in manifest_input.sources:
        payload_digest = _sign_source_with_key(
            source_input,
            key_id=key_id,
            root_key=root_key,
        )
        source_results.append(
            contracts.HealthDaySourceResult(
                source_kind=source_input.source_kind,
                source_role=source_input.source_role,
                revision=source_input.revision,
                payload_digest=payload_digest,
                acquired_at=source_input.acquired_at,
                cutoff=source_input.cutoff,
                freshness=source_input.freshness,
                availability=source_input.availability,
                error_code=source_input.error_code,
                tombstone_state=source_input.tombstone_state,
            )
        )
        source_payload_values.append((source_input.source_kind, source_input.value))

    unsigned_bundle = contracts.HealthDayShadowBundle.create(
        schema_version=manifest_input.schema_version,
        owner_id=manifest_input.owner_id,
        local_day=manifest_input.local_day,
        timezone=manifest_input.timezone,
        as_of=manifest_input.as_of,
        transaction=manifest_input.transaction,
        sources=tuple(source_results),
        source_payload_values=tuple(source_payload_values),
        shadow_manifest_digest="",
    )
    manifest_digest = _sign_manifest_with_key(
        unsigned_bundle.manifest,
        key_id=key_id,
        root_key=root_key,
    )
    return contracts.HealthDayShadowBundle.create(
        schema_version=manifest_input.schema_version,
        owner_id=manifest_input.owner_id,
        local_day=manifest_input.local_day,
        timezone=manifest_input.timezone,
        as_of=manifest_input.as_of,
        transaction=manifest_input.transaction,
        sources=tuple(source_results),
        source_payload_values=tuple(source_payload_values),
        shadow_manifest_digest=manifest_digest,
    )


def _verify_bundle_ownership_graph(
    bundle: contracts.HealthDayShadowBundle,
) -> None:
    try:
        manifest = bundle.manifest
        payloads = bundle.payloads
        if type(manifest) is not contracts.HealthDayShadowManifest or type(
            payloads
        ) is not tuple:
            return
        if not all(
            type(payload) is contracts.HealthDaySourcePayload for payload in payloads
        ):
            return
        ownership = bundle._bundle_ownership
        if (
            type(ownership) is not contracts._BundleOwnership
            or ownership.issuer is not contracts._BUNDLE_OWNERSHIP_ISSUER
            or manifest._bundle_ownership is not ownership
            or any(
            payload._bundle_ownership is not ownership for payload in payloads
            )
        ):
            _raise("shadow_digest_verification_failed:bundle_ownership")
    except ShadowSigningError:
        raise
    except Exception:
        _raise("shadow_digest_verification_failed:bundle_ownership")


def verify_digest_bound_shadow_bundle(
    bundle: contracts.HealthDayShadowBundle,
    key_provider: ShadowKeyProvider,
) -> None:
    if type(bundle) is not contracts.HealthDayShadowBundle:
        _raise("shadow_digest_verification_failed:bundle_type")
    _verify_bundle_ownership_graph(bundle)

    try:
        _revalidate_frozen_contract(
            bundle,
            "shadow_digest_verification_failed:structure",
        )
        manifest = bundle.manifest
        payloads = bundle.payloads
        if type(manifest) is not contracts.HealthDayShadowManifest:
            _raise("shadow_digest_verification_failed:structure")
        if type(payloads) is not tuple or len(payloads) != len(manifest.sources):
            _raise("shadow_digest_verification_failed:structure")
        source_projections: list[dict[str, object]] = []
        received_source_digests: list[str] = []
        source_inputs: list[SourceSigningInput] = []
        for source_result, source_payload in zip(manifest.sources, payloads):
            if (
                type(source_result) is not contracts.HealthDaySourceResult
                or type(source_payload) is not contracts.HealthDaySourcePayload
                or source_result.source_kind is not source_payload.source_kind
            ):
                _raise("shadow_digest_verification_failed:structure")
            _revalidate_frozen_contract(
                source_payload,
                "shadow_digest_verification_failed:structure",
            )
            _project_source_result(source_result)
            source_input = SourceSigningInput(
                source_kind=source_result.source_kind,
                source_role=source_result.source_role,
                revision=source_result.revision,
                acquired_at=source_result.acquired_at,
                cutoff=source_result.cutoff,
                freshness=source_result.freshness,
                availability=source_result.availability,
                error_code=source_result.error_code,
                tombstone_state=source_result.tombstone_state,
                value=source_payload.value,
            )
            source_inputs.append(source_input)
            source_projections.append(_project_source_signing_input(source_input))
            received_source_digests.append(source_result.payload_digest)
        manifest_input = ManifestSigningInput(
            schema_version=manifest.schema_version,
            owner_id=manifest.owner_id,
            local_day=manifest.local_day,
            timezone=manifest.timezone,
            as_of=manifest.as_of,
            transaction=manifest.transaction,
            sources=tuple(source_inputs),
        )
        del manifest_input
        manifest_projection = _project_manifest(manifest)
        received_manifest_digest = bundle.shadow_manifest_digest
    except ShadowSigningError:
        _raise("shadow_digest_verification_failed:structure")
    except Exception:
        _raise("shadow_digest_verification_failed:structure")

    key_id, root_key = _read_key(key_provider)
    for index, (source_projection, received_source_digest) in enumerate(
        zip(source_projections, received_source_digests)
    ):
        expected_source_digest = _sign_projected_payload(
            source_projection,
            purpose="source-payload",
            key_id=key_id,
            root_key=root_key,
        )
        if not hmac.compare_digest(
            expected_source_digest,
            received_source_digest,
        ):
            _raise(f"shadow_digest_verification_failed:source_payload:{index}")

    expected_manifest_digest = _sign_projected_payload(
        manifest_projection,
        purpose="manifest-digest",
        key_id=key_id,
        root_key=root_key,
    )
    if not hmac.compare_digest(
        expected_manifest_digest,
        received_manifest_digest,
    ):
        _raise("shadow_digest_verification_failed:manifest_digest")


def _project_transaction(
    transaction: contracts.HealthDayTransaction,
) -> dict[str, object]:
    if type(transaction) is not contracts.HealthDayTransaction:
        _raise("manifest_transaction_type_invalid")
    _revalidate_frozen_contract(transaction)
    return {
        "dialect": _require_enum(
            transaction.dialect,
            contracts.TransactionDialect,
            "manifest_transaction_field_invalid",
        ),
        "isolation": _require_enum(
            transaction.isolation,
            contracts.TransactionIsolation,
            "manifest_transaction_field_invalid",
        ),
        "read_only": _require_bool(
            transaction.read_only,
            "manifest_transaction_field_invalid",
        ),
    }


def _project_source_signing_input(
    source_input: SourceSigningInput,
) -> dict[str, object]:
    if type(source_input) is not SourceSigningInput:
        _raise("source_signing_input_type_invalid")
    source_kind = _require_enum(
        source_input.source_kind,
        contracts.HealthDaySourceKind,
        "source_signing_input_field_type_invalid",
    )
    return {
        "source_kind": source_kind,
        "source_role": _require_enum(
            source_input.source_role,
            contracts.HealthDaySourceRole,
            "source_signing_input_field_type_invalid",
        ),
        "revision": _require_optional_identifier(
            source_input.revision,
            "source_signing_input_field_type_invalid",
        ),
        "acquired_at": _optional_timestamp(
            source_input.acquired_at,
            "source_signing_input_field_type_invalid",
        ),
        "cutoff": _optional_timestamp(
            source_input.cutoff,
            "source_signing_input_field_type_invalid",
        ),
        "freshness": _require_enum(
            source_input.freshness,
            contracts.SourceFreshness,
            "source_signing_input_field_type_invalid",
        ),
        "availability": _require_enum(
            source_input.availability,
            contracts.SourceAvailability,
            "source_signing_input_field_type_invalid",
        ),
        "error_code": (
            None
            if source_input.error_code is None
            else _require_enum(
                source_input.error_code,
                contracts.ShadowReasonCode,
                "source_signing_input_field_type_invalid",
            )
        ),
        "tombstone_state": _require_enum(
            source_input.tombstone_state,
            contracts.TombstoneState,
            "source_signing_input_field_type_invalid",
        ),
        "value": _project_source_payload_value(
            source_input.source_kind,
            source_input.value,
        ),
    }


def _project_source_result(
    source: contracts.HealthDaySourceResult,
) -> dict[str, object]:
    if type(source) is not contracts.HealthDaySourceResult:
        _raise("shadow_manifest_source_type_invalid")
    _revalidate_frozen_contract(source)
    return {
        "source_kind": _require_enum(
            source.source_kind,
            contracts.HealthDaySourceKind,
            "shadow_manifest_source_field_invalid",
        ),
        "source_role": _require_enum(
            source.source_role,
            contracts.HealthDaySourceRole,
            "shadow_manifest_source_field_invalid",
        ),
        "revision": _require_optional_identifier(
            source.revision,
            "shadow_manifest_source_field_invalid",
        ),
        "payload_digest": _require_identifier(
            source.payload_digest,
            "shadow_manifest_source_field_invalid",
        ),
        "acquired_at": _optional_timestamp(
            source.acquired_at,
            "shadow_manifest_source_field_invalid",
        ),
        "cutoff": _optional_timestamp(
            source.cutoff,
            "shadow_manifest_source_field_invalid",
        ),
        "freshness": _require_enum(
            source.freshness,
            contracts.SourceFreshness,
            "shadow_manifest_source_field_invalid",
        ),
        "availability": _require_enum(
            source.availability,
            contracts.SourceAvailability,
            "shadow_manifest_source_field_invalid",
        ),
        "error_code": (
            None
            if source.error_code is None
            else _require_enum(
                source.error_code,
                contracts.ShadowReasonCode,
                "shadow_manifest_source_field_invalid",
            )
        ),
        "tombstone_state": _require_enum(
            source.tombstone_state,
            contracts.TombstoneState,
            "shadow_manifest_source_field_invalid",
        ),
    }


def _project_manifest(manifest: contracts.HealthDayShadowManifest) -> dict[str, object]:
    if type(manifest) is not contracts.HealthDayShadowManifest:
        _raise("shadow_manifest_type_invalid")
    _revalidate_frozen_contract(manifest)
    schema_version = _require_schema_version(
        manifest.schema_version,
        "manifest.schema_version",
    )
    owner_id = _require_owner_id(manifest.owner_id, "manifest.owner_id")
    local_day = _require_exact_date(manifest.local_day, "manifest.local_day")
    timezone_name = _require_timezone(manifest.timezone, "manifest.timezone")
    as_of = _require_utc_datetime(manifest.as_of, "manifest.as_of")
    _require_manifest_local_day_match(as_of, timezone_name, local_day)
    if type(manifest.sources) is not tuple:
        _raise("shadow_manifest_sources_tuple_required")
    kinds = tuple(source.source_kind for source in manifest.sources)
    if len(kinds) != len(set(kinds)):
        _raise("signing_sources_duplicate_kind")
    try:
        expected = tuple(sorted(kinds, key=_SOURCE_ORDER_INDEX.__getitem__))
    except KeyError:
        _raise("signing_source_kind_invalid")
    if kinds != expected:
        _raise("signing_sources_out_of_order")
    return {
        "schema_version": schema_version,
        "owner_id": owner_id,
        "local_day": local_day.isoformat(),
        "timezone": timezone_name,
        "as_of": _timestamp(as_of, "manifest.as_of"),
        "transaction": _project_transaction(manifest.transaction),
        "sources": [_project_source_result(source) for source in manifest.sources],
    }


def _project_item_identity(
    manifest_identity: ShadowManifestIdentity,
    item_identity: contracts.ShadowItemIdentity,
) -> dict[str, object]:
    if type(manifest_identity) is not ShadowManifestIdentity:
        _raise("manifest_identity_invalid")
    if type(item_identity) is not contracts.ShadowItemIdentity:
        _raise("item_identity_invalid")
    _revalidate_frozen_contract(item_identity, "item_identity_invalid")
    if type(item_identity.storage_namespace) is not contracts.StorageNamespace:
        _raise("item_identity_invalid")
    if item_identity.storage_namespace not in contracts.STORAGE_NAMESPACE_V1:
        _raise("item_identity_invalid")
    if type(item_identity.local_day) is not date:
        _raise("item_identity_invalid")
    if manifest_identity.local_day != item_identity.local_day:
        _raise("item_identity_local_day_mismatch")
    return {
        "schema_version": _require_schema_version(
            manifest_identity.schema_version,
            "manifest_identity.schema_version",
        ),
        "owner_id": _require_owner_id(
            manifest_identity.owner_id,
            "manifest_identity.owner_id",
        ),
        "local_day": manifest_identity.local_day.isoformat(),
        "storage_namespace": item_identity.storage_namespace.value,
        "source_kind": _require_enum(
            item_identity.source_kind,
            contracts.HealthDaySourceKind,
            "item_identity_invalid",
        ),
        "source_id": _require_identifier(
            item_identity.source_id,
            "item_identity_invalid",
        ),
        "slot_local_minute": _require_local_minute(
            item_identity.slot_local_minute,
            "item_identity_invalid",
        ),
        "dose_ordinal": _require_non_negative_int(
            item_identity.dose_ordinal,
            "item_identity_invalid",
        ),
        "projection_role": _require_enum(
            item_identity.projection_role,
            contracts.ProjectionRole,
            "item_identity_invalid",
        ),
    }


def _require_source_value_type(value: object, expected: type) -> None:
    if type(value) is not expected:
        _raise("source_value_schema_mismatch")


def _required_date_string(value: object, code: str) -> str:
    return _require_exact_date(value, code).isoformat()


def _require_optional_bool(value: object, code: str) -> bool | None:
    if value is None:
        return None
    return _require_bool(value, code)


def _project_profile_schedule(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ProfileScheduleDTO)
    profile: contracts.ProfileScheduleDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(profile)
    return {
        "timezone": _require_optional_string(profile.timezone, "profile.timezone"),
        "detected_timezone": _require_optional_string(
            profile.detected_timezone,
            "profile.detected_timezone",
        ),
        "manual_timezone": _require_optional_string(
            profile.manual_timezone,
            "profile.manual_timezone",
        ),
        "usual_sleep_time": _require_optional_string(
            profile.usual_sleep_time,
            "profile.usual_sleep_time",
        ),
        "usual_wake_time": _require_optional_string(
            profile.usual_wake_time,
            "profile.usual_wake_time",
        ),
        "work_start_time": _require_optional_string(
            profile.work_start_time,
            "profile.work_start_time",
        ),
        "work_end_time": _require_optional_string(
            profile.work_end_time,
            "profile.work_end_time",
        ),
        "workout_pref_window": _require_optional_string(
            profile.workout_pref_window,
            "profile.workout_pref_window",
        ),
        "workout_target_minutes": _require_optional_int(
            profile.workout_target_minutes,
            "profile.workout_target_minutes",
        ),
    }


def _project_body_weight(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.BodyWeightSubsetDTO)
    body_weight: contracts.BodyWeightSubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(body_weight)
    return {
        "record_date": _require_optional_date(
            body_weight.record_date,
            "body_weight.record_date",
        ),
        "weight_decimal": _require_optional_decimal_string(
            body_weight.weight_decimal,
            "body_weight.weight_decimal",
        ),
        "availability": _require_enum(
            body_weight.availability,
            contracts.SourceAvailability,
            "body_weight.availability",
        ),
        "competition": _require_enum(
            body_weight.competition,
            contracts.SourceCompetition,
            "body_weight.competition",
        ),
        "reason_codes": _reason_codes(
            body_weight.reason_codes,
            "body_weight.reason_codes",
        ),
    }


def _project_lab_anchor(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.LabAnchorSubsetDTO)
    lab_anchor: contracts.LabAnchorSubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(lab_anchor)
    return {
        "availability": _require_enum(
            lab_anchor.availability,
            contracts.SourceAvailability,
            "lab_anchor.availability",
        ),
        "anchor_missing": _require_bool(
            lab_anchor.anchor_missing,
            "lab_anchor.anchor_missing",
        ),
        "anchor_stale": _require_bool(
            lab_anchor.anchor_stale,
            "lab_anchor.anchor_stale",
        ),
        "reason_codes": _reason_codes(
            lab_anchor.reason_codes,
            "lab_anchor.reason_codes",
        ),
    }


def _project_recovery_wearable(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.RecoveryWearableFactDTO)
    wearable: contracts.RecoveryWearableFactDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(wearable)
    return {
        "fact_kind": _require_enum(
            wearable.fact_kind,
            contracts.WearableFactKind,
            "recovery_wearable.fact_kind",
        ),
        "record_date": _require_optional_date(
            wearable.record_date,
            "recovery_wearable.record_date",
        ),
        "value_decimal": _require_optional_decimal_string(
            wearable.value_decimal,
            "recovery_wearable.value_decimal",
        ),
        "freshness": _require_enum(
            wearable.freshness,
            contracts.SourceFreshness,
            "recovery_wearable.freshness",
        ),
        "competition": _require_enum(
            wearable.competition,
            contracts.SourceCompetition,
            "recovery_wearable.competition",
        ),
        "reason_codes": _reason_codes(
            wearable.reason_codes,
            "recovery_wearable.reason_codes",
        ),
    }


def _project_acute(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.AcuteSubsetDTO)
    acute: contracts.AcuteSubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(acute)
    return {
        "has_active_illness": _require_bool(
            acute.has_active_illness,
            "acute.has_active_illness",
        ),
        "suspected_cold": _require_bool(
            acute.suspected_cold,
            "acute.suspected_cold",
        ),
        "fever_reported": _require_bool(
            acute.fever_reported,
            "acute.fever_reported",
        ),
        "should_rest": _require_bool(acute.should_rest, "acute.should_rest"),
        "guardrail_code": _require_enum(
            acute.guardrail_code,
            contracts.AcuteGuardrailCode,
            "acute.guardrail_code",
        ),
        "severity_max": _require_optional_int(
            acute.severity_max,
            "acute.severity_max",
        ),
        "classification_status": _require_enum(
            acute.classification_status,
            contracts.ClassifierStatus,
            "acute.classification_status",
        ),
        "classifier_version": _require_identifier(
            acute.classifier_version,
            "acute.classifier_version",
        ),
        "classifier_policy_digest": _require_identifier(
            acute.classifier_policy_digest,
            "acute.classifier_policy_digest",
        ),
        "availability": _require_enum(
            acute.availability,
            contracts.SourceAvailability,
            "acute.availability",
        ),
        "reason_codes": _reason_codes(acute.reason_codes, "acute.reason_codes"),
    }


def _project_recovery(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.RecoverySubsetDTO)
    recovery: contracts.RecoverySubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(recovery)
    return {
        "sleep": _project_recovery_wearable(recovery.sleep),
        "readiness": _project_recovery_wearable(recovery.readiness),
        "acute": _project_acute(recovery.acute),
        "poor_recovery": _require_optional_bool(
            recovery.poor_recovery,
            "recovery.poor_recovery",
        ),
        "availability": _require_enum(
            recovery.availability,
            contracts.SourceAvailability,
            "recovery.availability",
        ),
        "reason_codes": _reason_codes(
            recovery.reason_codes,
            "recovery.reason_codes",
        ),
    }


def _project_intervention(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.InterventionSubsetDTO)
    intervention: contracts.InterventionSubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(intervention)
    return {
        "action_key": _require_identifier(
            intervention.action_key,
            "intervention.action_key",
        ),
        "priority": _require_int(intervention.priority, "intervention.priority"),
        "created_at": _timestamp(
            intervention.created_at,
            "intervention.created_at",
        ),
        "expires_at": _optional_timestamp(
            intervention.expires_at,
            "intervention.expires_at",
        ),
        "metric_key": _require_optional_identifier(
            intervention.metric_key,
            "intervention.metric_key",
        ),
        "target_value_decimal": _require_optional_decimal_string(
            intervention.target_value_decimal,
            "intervention.target_value_decimal",
        ),
        "evidence_level": _require_optional_identifier(
            intervention.evidence_level,
            "intervention.evidence_level",
        ),
        "check_back_date": _require_optional_date(
            intervention.check_back_date,
            "intervention.check_back_date",
        ),
        "classification_status": _require_enum(
            intervention.classification_status,
            contracts.ClassifierStatus,
            "intervention.classification_status",
        ),
        "training_like": _require_optional_bool(
            intervention.training_like,
            "intervention.training_like",
        ),
        "classifier_version": _require_identifier(
            intervention.classifier_version,
            "intervention.classifier_version",
        ),
        "classifier_policy_digest": _require_identifier(
            intervention.classifier_policy_digest,
            "intervention.classifier_policy_digest",
        ),
        "domain": _require_enum(
            intervention.domain,
            contracts.HealthDomain,
            "intervention.domain",
        ),
        "availability": _require_enum(
            intervention.availability,
            contracts.SourceAvailability,
            "intervention.availability",
        ),
        "reason_codes": _reason_codes(
            intervention.reason_codes,
            "intervention.reason_codes",
        ),
    }


def _project_terminal_action(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.TerminalActionSubsetDTO)
    terminal: contracts.TerminalActionSubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(terminal)
    return {
        "record_id": _require_identifier(terminal.record_id, "terminal.record_id"),
        "action_key": _require_identifier(
            terminal.action_key,
            "terminal.action_key",
        ),
        "status": _require_enum(
            terminal.status,
            contracts.CanonicalLifecycle,
            "terminal.status",
        ),
        "completion_provenance": _require_enum(
            terminal.completion_provenance,
            contracts.CompletionProvenance,
            "terminal.completion_provenance",
        ),
    }


def _project_active_cycle(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ActiveCycleSubsetDTO)
    cycle: contracts.ActiveCycleSubsetDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(cycle)
    return {
        "cycle_id": _require_identifier(cycle.cycle_id, "cycle.cycle_id"),
        "cycle_type": _require_identifier(cycle.cycle_type, "cycle.cycle_type"),
        "start_date": _required_date_string(cycle.start_date, "cycle.start_date"),
        "planned_end_date": _require_optional_date(
            cycle.planned_end_date,
            "cycle.planned_end_date",
        ),
        "primary_metric_code": _require_optional_identifier(
            cycle.primary_metric_code,
            "cycle.primary_metric_code",
        ),
        "outcome_status": _require_optional_identifier(
            cycle.outcome_status,
            "cycle.outcome_status",
        ),
        "availability": _require_enum(
            cycle.availability,
            contracts.SourceAvailability,
            "cycle.availability",
        ),
        "reason_codes": _reason_codes(cycle.reason_codes, "cycle.reason_codes"),
    }


def _project_existing_dop_action(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ExistingDOPActionFact)
    action: contracts.ExistingDOPActionFact = value  # type: ignore[assignment]
    _revalidate_frozen_contract(action)
    return {
        "action_key": _require_identifier(action.action_key, "dop_action.action_key"),
        "domain": _require_enum(
            action.domain,
            contracts.HealthDomain,
            "dop_action.domain",
        ),
        "when_code": _require_optional_identifier(
            action.when_code,
            "dop_action.when_code",
        ),
    }


def _project_existing_dop(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ExistingDOPDiagnosticDTO)
    dop: contracts.ExistingDOPDiagnosticDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(dop)
    if type(dop.actions) is not tuple:
        _raise("source_value_schema_mismatch")
    return {
        "plan_id": _require_identifier(dop.plan_id, "existing_dop.plan_id"),
        "status": _require_enum(
            dop.status,
            contracts.DailyPlanStatus,
            "existing_dop.status",
        ),
        "actions": [_project_existing_dop_action(action) for action in dop.actions],
        "availability": _require_enum(
            dop.availability,
            contracts.SourceAvailability,
            "existing_dop.availability",
        ),
        "reason_codes": _reason_codes(
            dop.reason_codes,
            "existing_dop.reason_codes",
        ),
    }


def _project_daily_plan_subset(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.DailyPlanSubsetFactsDTO)
    daily_plan: contracts.DailyPlanSubsetFactsDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(daily_plan)
    if type(daily_plan.interventions) is not tuple:
        _raise("source_value_schema_mismatch")
    if type(daily_plan.terminal_actions) is not tuple:
        _raise("source_value_schema_mismatch")
    return {
        "body_weight": _project_body_weight(daily_plan.body_weight),
        "lab_anchor": _project_lab_anchor(daily_plan.lab_anchor),
        "recovery": _project_recovery(daily_plan.recovery),
        "interventions": [
            _project_intervention(intervention)
            for intervention in daily_plan.interventions
        ],
        "terminal_actions": [
            _project_terminal_action(terminal)
            for terminal in daily_plan.terminal_actions
        ],
        "active_cycle": (
            None
            if daily_plan.active_cycle is None
            else _project_active_cycle(daily_plan.active_cycle)
        ),
        "existing_dop": (
            None
            if daily_plan.existing_dop is None
            else _project_existing_dop(daily_plan.existing_dop)
        ),
        "reason_codes": _reason_codes(
            daily_plan.reason_codes,
            "daily_plan.reason_codes",
        ),
    }


def _project_program_inventory(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ProgramInventoryDTO)
    program: contracts.ProgramInventoryDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(program)
    return {
        "program_id": _require_identifier(program.program_id, "program.program_id"),
        "program_type": _require_identifier(
            program.program_type,
            "program.program_type",
        ),
        "problem_id": _require_optional_identifier(
            program.problem_id,
            "program.problem_id",
        ),
        "started_on": _required_date_string(
            program.started_on,
            "program.started_on",
        ),
        "target_end_on": _require_optional_date(
            program.target_end_on,
            "program.target_end_on",
        ),
        "availability": _require_enum(
            program.availability,
            contracts.SourceAvailability,
            "program.availability",
        ),
        "reason_codes": _reason_codes(
            program.reason_codes,
            "program.reason_codes",
        ),
    }


def _project_protocol(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ProtocolDTO)
    protocol: contracts.ProtocolDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(protocol)
    return {
        "protocol_id": _require_identifier(
            protocol.protocol_id,
            "protocol.protocol_id",
        ),
        "domain": _require_enum(
            protocol.domain,
            contracts.HealthDomain,
            "protocol.domain",
        ),
        "mechanism": _require_optional_string(
            protocol.mechanism,
            "protocol.mechanism",
        ),
        "cadence": _require_enum(
            protocol.cadence,
            contracts.ProtocolCadence,
            "protocol.cadence",
        ),
        "time_window": _require_optional_string(
            protocol.time_window,
            "protocol.time_window",
        ),
        "completion_mode": _require_enum(
            protocol.completion_mode,
            contracts.ProtocolCompletionMode,
            "protocol.completion_mode",
        ),
        "can_default_complete": _require_bool(
            protocol.can_default_complete,
            "protocol.can_default_complete",
        ),
        "manual_track_allowed": _require_bool(
            protocol.manual_track_allowed,
            "protocol.manual_track_allowed",
        ),
        "program_id": _require_optional_identifier(
            protocol.program_id,
            "protocol.program_id",
        ),
        "source_model": _require_optional_identifier(
            protocol.source_model,
            "protocol.source_model",
        ),
        "source_id": _require_optional_identifier(
            protocol.source_id,
            "protocol.source_id",
        ),
        "trigger_date": _require_optional_date(
            protocol.trigger_date,
            "protocol.trigger_date",
        ),
        "availability": _require_enum(
            protocol.availability,
            contracts.SourceAvailability,
            "protocol.availability",
        ),
        "reason_codes": _reason_codes(
            protocol.reason_codes,
            "protocol.reason_codes",
        ),
    }


def _project_protocol_event(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ProtocolEventDTO)
    event: contracts.ProtocolEventDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(event)
    return {
        "event_id": _require_identifier(event.event_id, "protocol_event.event_id"),
        "protocol_id": _require_identifier(
            event.protocol_id,
            "protocol_event.protocol_id",
        ),
        "event_date": _required_date_string(
            event.event_date,
            "protocol_event.event_date",
        ),
        "status": _require_enum(
            event.status,
            contracts.CanonicalLifecycle,
            "protocol_event.status",
        ),
        "track": _require_optional_identifier(event.track, "protocol_event.track"),
        "snoozed_until": _optional_timestamp(
            event.snoozed_until,
            "protocol_event.snoozed_until",
        ),
        "reason_codes": _reason_codes(
            event.reason_codes,
            "protocol_event.reason_codes",
        ),
    }


def _project_problem_followup(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.ProblemFollowUpDTO)
    problem: contracts.ProblemFollowUpDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(problem)
    return {
        "problem_id": _require_identifier(problem.problem_id, "problem.problem_id"),
        "risk_level": _require_enum(
            problem.risk_level,
            contracts.ProblemRiskLevel,
            "problem.risk_level",
        ),
        "status": _require_enum(
            problem.status,
            contracts.ProblemStatus,
            "problem.status",
        ),
        "last_checkup": _require_optional_date(
            problem.last_checkup,
            "problem.last_checkup",
        ),
        "cadence": _require_enum(
            problem.cadence,
            contracts.ProtocolCadence,
            "problem.cadence",
        ),
        "next_due": _require_optional_date(problem.next_due, "problem.next_due"),
        "reason_codes": _reason_codes(
            problem.reason_codes,
            "problem.reason_codes",
        ),
    }


def _project_medication_source(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.MedicationSourceDTO)
    medication: contracts.MedicationSourceDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(medication)
    if type(medication.normalized_slots) is not tuple:
        _raise("source_value_schema_mismatch")
    return {
        "storage_namespace": _require_enum(
            medication.storage_namespace,
            contracts.StorageNamespace,
            "medication.storage_namespace",
        ),
        "medication_id": _require_identifier(
            medication.medication_id,
            "medication.medication_id",
        ),
        "times_per_day": _require_non_negative_int(
            medication.times_per_day,
            "medication.times_per_day",
        ),
        "normalized_slots": [
            _require_local_minute(slot, "medication.normalized_slots")
            for slot in medication.normalized_slots
        ],
        "domain": _require_enum(
            medication.domain,
            contracts.HealthDomain,
            "medication.domain",
        ),
        "domain_classification_provenance": _require_enum(
            medication.domain_classification_provenance,
            contracts.DomainClassificationProvenance,
            "medication.domain_classification_provenance",
        ),
        "domain_classifier_version": _require_identifier(
            medication.domain_classifier_version,
            "medication.domain_classifier_version",
        ),
        "domain_classifier_policy_digest": _require_identifier(
            medication.domain_classifier_policy_digest,
            "medication.domain_classifier_policy_digest",
        ),
        "timing_relation": _require_enum(
            medication.timing_relation,
            contracts.TimingRelation,
            "medication.timing_relation",
        ),
        "meal_anchor": _require_enum(
            medication.meal_anchor,
            contracts.MealAnchor,
            "medication.meal_anchor",
        ),
        "start_date": _require_optional_date(
            medication.start_date,
            "medication.start_date",
        ),
        "end_date": _require_optional_date(
            medication.end_date,
            "medication.end_date",
        ),
        "occurrence_availability": _require_enum(
            medication.occurrence_availability,
            contracts.OccurrenceAvailability,
            "medication.occurrence_availability",
        ),
        "reason_codes": _reason_codes(
            medication.reason_codes,
            "medication.reason_codes",
        ),
    }


def _project_medication_execution(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.MedicationExecutionDTO)
    execution: contracts.MedicationExecutionDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(execution)
    return {
        "record_id": _require_identifier(
            execution.record_id,
            "medication_execution.record_id",
        ),
        "medication_id": _require_identifier(
            execution.medication_id,
            "medication_execution.medication_id",
        ),
        "taken_date": _required_date_string(
            execution.taken_date,
            "medication_execution.taken_date",
        ),
        "raw_slot_present": _require_bool(
            execution.raw_slot_present,
            "medication_execution.raw_slot_present",
        ),
        "normalized_slot": _require_local_minute(
            execution.normalized_slot,
            "medication_execution.normalized_slot",
        ),
        "status": _require_enum(
            execution.status,
            contracts.CanonicalLifecycle,
            "medication_execution.status",
        ),
        "match_disposition": _require_enum(
            execution.match_disposition,
            contracts.ExecutionMatchDisposition,
            "medication_execution.match_disposition",
        ),
        "reason_codes": _reason_codes(
            execution.reason_codes,
            "medication_execution.reason_codes",
        ),
    }


def _project_supplement_source(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.SupplementSourceDTO)
    supplement: contracts.SupplementSourceDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(supplement)
    return {
        "storage_namespace": _require_enum(
            supplement.storage_namespace,
            contracts.StorageNamespace,
            "supplement.storage_namespace",
        ),
        "supplement_definition_id": _require_identifier(
            supplement.supplement_definition_id,
            "supplement.supplement_definition_id",
        ),
        "timing_label": _require_enum(
            supplement.timing_label,
            contracts.SupplementTimingLabel,
            "supplement.timing_label",
        ),
        "timing_precision_status": _require_enum(
            supplement.timing_precision_status,
            contracts.TimingPrecision,
            "supplement.timing_precision_status",
        ),
        "sort_order": _require_int(
            supplement.sort_order,
            "supplement.sort_order",
        ),
        "reason_codes": _reason_codes(
            supplement.reason_codes,
            "supplement.reason_codes",
        ),
    }


def _project_supplement_execution(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.SupplementExecutionDTO)
    execution: contracts.SupplementExecutionDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(execution)
    return {
        "record_id": _require_identifier(
            execution.record_id,
            "supplement_execution.record_id",
        ),
        "supplement_definition_id": _require_identifier(
            execution.supplement_definition_id,
            "supplement_execution.supplement_definition_id",
        ),
        "record_date": _required_date_string(
            execution.record_date,
            "supplement_execution.record_date",
        ),
        "normalized_time": _require_local_minute(
            execution.normalized_time,
            "supplement_execution.normalized_time",
        ),
        "taken": _require_bool(execution.taken, "supplement_execution.taken"),
        "reason_codes": _reason_codes(
            execution.reason_codes,
            "supplement_execution.reason_codes",
        ),
    }


def _project_calendar_source(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.CalendarSourceFact)
    source: contracts.CalendarSourceFact = value  # type: ignore[assignment]
    _revalidate_frozen_contract(source)
    return {
        "source_id": _require_identifier(source.source_id, "calendar_source.source_id"),
        "provider_code": _require_identifier(
            source.provider_code,
            "calendar_source.provider_code",
        ),
        "sync_enabled": _require_bool(
            source.sync_enabled,
            "calendar_source.sync_enabled",
        ),
        "last_sync_at": _optional_timestamp(
            source.last_sync_at,
            "calendar_source.last_sync_at",
        ),
        "sync_failed": _require_bool(
            source.sync_failed,
            "calendar_source.sync_failed",
        ),
    }


def _project_calendar_interval(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.CalendarIntervalFact)
    interval: contracts.CalendarIntervalFact = value  # type: ignore[assignment]
    _revalidate_frozen_contract(interval)
    return {
        "event_id": _require_identifier(
            interval.event_id,
            "calendar_interval.event_id",
        ),
        "source_id": _require_identifier(
            interval.source_id,
            "calendar_interval.source_id",
        ),
        "start_utc": _optional_timestamp(
            interval.start_utc,
            "calendar_interval.start_utc",
        ),
        "end_utc": _optional_timestamp(
            interval.end_utc,
            "calendar_interval.end_utc",
        ),
        "all_day": _require_bool(interval.all_day, "calendar_interval.all_day"),
        "local_start_minute": _require_local_minute(
            interval.local_start_minute,
            "calendar_interval.local_start_minute",
        ),
        "local_end_minute": _require_local_minute(
            interval.local_end_minute,
            "calendar_interval.local_end_minute",
        ),
        "utc_offset_start_minutes": _require_optional_int(
            interval.utc_offset_start_minutes,
            "calendar_interval.utc_offset_start_minutes",
        ),
        "utc_offset_end_minutes": _require_optional_int(
            interval.utc_offset_end_minutes,
            "calendar_interval.utc_offset_end_minutes",
        ),
        "fold_start": _require_optional_int(
            interval.fold_start,
            "calendar_interval.fold_start",
        ),
        "fold_end": _require_optional_int(
            interval.fold_end,
            "calendar_interval.fold_end",
        ),
        "crosses_midnight": _require_optional_bool(
            interval.crosses_midnight,
            "calendar_interval.crosses_midnight",
        ),
        "reason_codes": _reason_codes(
            interval.reason_codes,
            "calendar_interval.reason_codes",
        ),
    }


def _project_calendar_knowledge(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.CalendarKnowledgeDTO)
    calendar: contracts.CalendarKnowledgeDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(calendar)
    if type(calendar.sources) is not tuple or type(calendar.intervals) is not tuple:
        _raise("source_value_schema_mismatch")
    return {
        "state": _require_enum(
            calendar.state,
            contracts.CalendarKnowledgeState,
            "calendar.state",
        ),
        "effective_timezone": _require_timezone(
            calendar.effective_timezone,
            "calendar.effective_timezone",
        ),
        "day_start_utc": _timestamp(
            calendar.day_start_utc,
            "calendar.day_start_utc",
        ),
        "day_end_utc": _timestamp(
            calendar.day_end_utc,
            "calendar.day_end_utc",
        ),
        "sources": [_project_calendar_source(source) for source in calendar.sources],
        "intervals": [
            _project_calendar_interval(interval) for interval in calendar.intervals
        ],
        "reason_codes": _reason_codes(
            calendar.reason_codes,
            "calendar.reason_codes",
        ),
    }


def _project_safety_seam(value: object) -> dict[str, object]:
    _require_source_value_type(value, contracts.SafetySeamDTO)
    safety: contracts.SafetySeamDTO = value  # type: ignore[assignment]
    _revalidate_frozen_contract(safety)
    return {
        "availability": _require_enum(
            safety.availability,
            contracts.SourceAvailability,
            "safety.availability",
        ),
        "disposition": _require_enum(
            safety.disposition,
            contracts.SafetyDisposition,
            "safety.disposition",
        ),
        "reason_codes": _reason_codes(safety.reason_codes, "safety.reason_codes"),
    }


def _project_program_inventory_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_program_inventory(member) for member in value]


def _project_protocols_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_protocol(member) for member in value]


def _project_protocol_events_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_protocol_event(member) for member in value]


def _project_problem_followups_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_problem_followup(member) for member in value]


def _project_medications_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_medication_source(member) for member in value]


def _project_medication_executions_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_medication_execution(member) for member in value]


def _project_supplements_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_supplement_source(member) for member in value]


def _project_supplement_executions_source(value: object) -> list[dict[str, object]]:
    if type(value) is not tuple:
        _raise("source_value_schema_mismatch")
    return [_project_supplement_execution(member) for member in value]


_SOURCE_PAYLOAD_PROJECTORS = {
    contracts.HealthDaySourceKind.PROFILE_SCHEDULE: _project_profile_schedule,
    contracts.HealthDaySourceKind.DAILY_PLAN_SUBSET: _project_daily_plan_subset,
    contracts.HealthDaySourceKind.PROGRAM_INVENTORY: _project_program_inventory_source,
    contracts.HealthDaySourceKind.PROTOCOLS: _project_protocols_source,
    contracts.HealthDaySourceKind.PROTOCOL_EVENTS: _project_protocol_events_source,
    contracts.HealthDaySourceKind.PROBLEM_FOLLOWUPS: _project_problem_followups_source,
    contracts.HealthDaySourceKind.MEDICATIONS: _project_medications_source,
    contracts.HealthDaySourceKind.MEDICATION_EXECUTIONS: (
        _project_medication_executions_source
    ),
    contracts.HealthDaySourceKind.SUPPLEMENTS: _project_supplements_source,
    contracts.HealthDaySourceKind.SUPPLEMENT_EXECUTIONS: (
        _project_supplement_executions_source
    ),
    contracts.HealthDaySourceKind.CALENDAR: _project_calendar_knowledge,
    contracts.HealthDaySourceKind.SAFETY: _project_safety_seam,
}


def _project_source_payload_value(
    source_kind: contracts.HealthDaySourceKind,
    value: contracts.SourcePayloadValue,
) -> object:
    if type(source_kind) is not contracts.HealthDaySourceKind:
        _raise("source_signing_input_field_type_invalid")
    projector = _SOURCE_PAYLOAD_PROJECTORS.get(source_kind)
    if projector is None:
        _raise("source_value_schema_mismatch")
    try:
        return projector(value)
    except ShadowSigningError:
        raise
    except Exception:
        _raise("source_value_schema_mismatch")


__all__ = (
    "HEALTH_DAY_SHADOW_DOMAIN",
    "ManifestSigningInput",
    "ShadowKeyProvider",
    "ShadowManifestIdentity",
    "ShadowSigningError",
    "SourceSigningInput",
    "bind_signed_shadow_item_key",
    "build_digest_bound_shadow_bundle",
    "canonical_shadow_jcs_subset_bytes",
    "sign_shadow_item_identity",
    "sign_shadow_manifest",
    "sign_shadow_source_payload",
    "verify_digest_bound_shadow_bundle",
)
