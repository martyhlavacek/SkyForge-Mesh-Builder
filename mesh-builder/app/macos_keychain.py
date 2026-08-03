from __future__ import annotations

import ctypes
from ctypes import POINTER, byref, c_char_p, c_int32, c_long, c_uint8, c_void_p

ERR_SEC_SUCCESS = 0
ERR_SEC_DUPLICATE_ITEM = -25299
ERR_SEC_ITEM_NOT_FOUND = -25300
ERR_SEC_USER_CANCELED = -128


def normalize_osstatus(value: int) -> int:
    """Normalize Security.framework's signed 32-bit OSStatus ABI.

    ctypes must not interpret OSStatus as C long on 64-bit macOS.  Defensive
    normalization also handles a zero-extended value returned by an incorrectly
    declared or mocked foreign function.
    """
    return int(c_int32(int(value)).value)


class KeychainError(RuntimeError):
    """Raised when Apple's Security framework rejects a keychain operation."""


class KeychainUserCancelled(KeychainError):
    """The user declined or cancelled a Keychain authorization prompt."""


class MacOSKeychain:
    """Minimal native wrapper around SecItem* for generic-password storage.

    The secret stays inside the current process and is passed to Security.framework
    as CFData. It is never placed in a command line, environment variable, log, or
    temporary file.
    """

    def __init__(self) -> None:
        try:
            self.security = ctypes.CDLL(
                '/System/Library/Frameworks/Security.framework/Security'
            )
            self.core = ctypes.CDLL(
                '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
            )
        except OSError as exc:
            raise KeychainError('macOS Security framework is unavailable') from exc
        self._configure_functions()
        self._load_constants()

    def _configure_functions(self) -> None:
        self.core.CFStringCreateWithCString.argtypes = [c_void_p, c_char_p, c_long]
        self.core.CFStringCreateWithCString.restype = c_void_p
        self.core.CFDataCreate.argtypes = [c_void_p, POINTER(c_uint8), c_long]
        self.core.CFDataCreate.restype = c_void_p
        self.core.CFDictionaryCreate.argtypes = [
            c_void_p,
            POINTER(c_void_p),
            POINTER(c_void_p),
            c_long,
            c_void_p,
            c_void_p,
        ]
        self.core.CFDictionaryCreate.restype = c_void_p
        self.core.CFDataGetLength.argtypes = [c_void_p]
        self.core.CFDataGetLength.restype = c_long
        self.core.CFDataGetBytePtr.argtypes = [c_void_p]
        self.core.CFDataGetBytePtr.restype = POINTER(c_uint8)
        self.core.CFRelease.argtypes = [c_void_p]
        self.core.CFRelease.restype = None

        self.security.SecItemAdd.argtypes = [c_void_p, POINTER(c_void_p)]
        self.security.SecItemAdd.restype = c_int32
        self.security.SecItemUpdate.argtypes = [c_void_p, c_void_p]
        self.security.SecItemUpdate.restype = c_int32
        self.security.SecItemCopyMatching.argtypes = [c_void_p, POINTER(c_void_p)]
        self.security.SecItemCopyMatching.restype = c_int32
        self.security.SecItemDelete.argtypes = [c_void_p]
        self.security.SecItemDelete.restype = c_int32

    @staticmethod
    def _symbol(library: ctypes.CDLL, name: str) -> c_void_p:
        return c_void_p.in_dll(library, name)

    def _load_constants(self) -> None:
        self.k_sec_class = self._symbol(self.security, 'kSecClass')
        self.k_sec_class_generic_password = self._symbol(
            self.security, 'kSecClassGenericPassword'
        )
        self.k_sec_attr_account = self._symbol(self.security, 'kSecAttrAccount')
        self.k_sec_attr_service = self._symbol(self.security, 'kSecAttrService')
        self.k_sec_value_data = self._symbol(self.security, 'kSecValueData')
        self.k_sec_return_data = self._symbol(self.security, 'kSecReturnData')
        self.k_sec_match_limit = self._symbol(self.security, 'kSecMatchLimit')
        self.k_sec_match_limit_one = self._symbol(self.security, 'kSecMatchLimitOne')
        self.k_cf_boolean_true = self._symbol(self.core, 'kCFBooleanTrue')

    def _cf_string(self, value: str) -> c_void_p:
        # kCFStringEncodingUTF8
        result = self.core.CFStringCreateWithCString(None, value.encode('utf-8'), 0x08000100)
        if not result:
            raise KeychainError('Could not encode a Keychain attribute')
        return c_void_p(result)

    def _cf_data(self, value: bytes) -> c_void_p:
        buffer = (c_uint8 * len(value)).from_buffer_copy(value)
        result = self.core.CFDataCreate(None, buffer, len(value))
        if not result:
            raise KeychainError('Could not encode Keychain secret data')
        return c_void_p(result)

    def _dictionary(self, pairs: list[tuple[c_void_p, c_void_p]]) -> c_void_p:
        keys = (c_void_p * len(pairs))(*(key.value for key, _ in pairs))
        values = (c_void_p * len(pairs))(*(value.value for _, value in pairs))
        # Null callbacks are safe for this synchronous use: the owned values remain
        # live until the SecItem call returns, and the dictionary is then released.
        result = self.core.CFDictionaryCreate(
            None, keys, values, len(pairs), None, None
        )
        if not result:
            raise KeychainError('Could not create a Keychain request')
        return c_void_p(result)

    def _base_query(self, service: str, account: str) -> tuple[c_void_p, list[c_void_p]]:
        service_ref = self._cf_string(service)
        account_ref = self._cf_string(account)
        query = self._dictionary([
            (self.k_sec_class, self.k_sec_class_generic_password),
            (self.k_sec_attr_service, service_ref),
            (self.k_sec_attr_account, account_ref),
        ])
        return query, [service_ref, account_ref]

    def _release_all(self, *values: c_void_p | None) -> None:
        for value in values:
            if value and value.value:
                self.core.CFRelease(value)

    @staticmethod
    def _status_error(operation: str, status: int) -> KeychainError:
        normalized = normalize_osstatus(status)
        error_type = KeychainUserCancelled if normalized == ERR_SEC_USER_CANCELED else KeychainError
        return error_type(f'macOS Keychain {operation} failed (OSStatus {normalized})')

    def read(self, service: str, account: str) -> str | None:
        base, owned = self._base_query(service, account)
        query = None
        result = c_void_p()
        try:
            query = self._dictionary([
                (self.k_sec_class, self.k_sec_class_generic_password),
                (self.k_sec_attr_service, owned[0]),
                (self.k_sec_attr_account, owned[1]),
                (self.k_sec_return_data, self.k_cf_boolean_true),
                (self.k_sec_match_limit, self.k_sec_match_limit_one),
            ])
            status = normalize_osstatus(self.security.SecItemCopyMatching(query, byref(result)))
            if status == ERR_SEC_ITEM_NOT_FOUND:
                return None
            if status != ERR_SEC_SUCCESS:
                raise self._status_error('read', status)
            length = int(self.core.CFDataGetLength(result))
            pointer = self.core.CFDataGetBytePtr(result)
            return bytes(pointer[index] for index in range(length)).decode('utf-8')
        finally:
            self._release_all(result, query, base, *owned)

    def write(self, service: str, account: str, secret: str) -> None:
        query, owned = self._base_query(service, account)
        secret_ref = self._cf_data(secret.encode('utf-8'))
        add_query = None
        update_values = None
        try:
            add_query = self._dictionary([
                (self.k_sec_class, self.k_sec_class_generic_password),
                (self.k_sec_attr_service, owned[0]),
                (self.k_sec_attr_account, owned[1]),
                (self.k_sec_value_data, secret_ref),
            ])
            status = normalize_osstatus(self.security.SecItemAdd(add_query, None))
            if status == ERR_SEC_DUPLICATE_ITEM:
                update_values = self._dictionary([(self.k_sec_value_data, secret_ref)])
                status = normalize_osstatus(self.security.SecItemUpdate(query, update_values))
            if status != ERR_SEC_SUCCESS:
                raise self._status_error('write', status)
        finally:
            self._release_all(update_values, add_query, secret_ref, query, *owned)

    def delete(self, service: str, account: str) -> None:
        query, owned = self._base_query(service, account)
        try:
            status = normalize_osstatus(self.security.SecItemDelete(query))
            if status not in {ERR_SEC_SUCCESS, ERR_SEC_ITEM_NOT_FOUND}:
                raise self._status_error('delete', status)
        finally:
            self._release_all(query, *owned)
