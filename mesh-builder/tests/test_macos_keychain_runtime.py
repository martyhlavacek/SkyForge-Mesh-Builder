from __future__ import annotations

from ctypes import c_int32, c_void_p
from types import SimpleNamespace

from app.macos_keychain import (
    ERR_SEC_DUPLICATE_ITEM,
    ERR_SEC_USER_CANCELED,
    KeychainUserCancelled,
    MacOSKeychain,
    normalize_osstatus,
)


def test_osstatus_normalizes_zero_extended_negative_values():
    assert normalize_osstatus(4294941997) == ERR_SEC_DUPLICATE_ITEM
    assert normalize_osstatus(4294967168) == ERR_SEC_USER_CANCELED
    assert normalize_osstatus(c_int32(ERR_SEC_DUPLICATE_ITEM).value) == ERR_SEC_DUPLICATE_ITEM


def test_duplicate_add_uses_update_even_when_status_is_zero_extended():
    calls: list[str] = []
    backend = MacOSKeychain.__new__(MacOSKeychain)
    backend.security = SimpleNamespace(
        SecItemAdd=lambda _query, _result: 4294941997,
        SecItemUpdate=lambda _query, _values: calls.append('update') or 0,
    )
    backend._base_query = lambda _service, _account: (c_void_p(1), [c_void_p(2), c_void_p(3)])
    backend._cf_data = lambda _value: c_void_p(4)
    backend._dictionary = lambda _pairs: c_void_p(5)
    backend._release_all = lambda *_values: None
    backend.k_sec_class = c_void_p(10)
    backend.k_sec_class_generic_password = c_void_p(11)
    backend.k_sec_attr_service = c_void_p(12)
    backend.k_sec_attr_account = c_void_p(13)
    backend.k_sec_value_data = c_void_p(14)

    backend.write('service', 'account', 'secret')

    assert calls == ['update']


def test_zero_extended_user_cancel_is_classified_without_unsigned_error_text():
    error = MacOSKeychain._status_error('read', 4294967168)
    assert isinstance(error, KeychainUserCancelled)
    assert 'OSStatus -128' in str(error)
