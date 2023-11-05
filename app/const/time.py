import datetime

import app.const.stdint as stdint

DATETIME_CLASSES = (datetime.datetime, datetime.date, datetime.time)


# ========== Timezone ==========
UTC = datetime.timezone.utc
KST = datetime.timezone(datetime.timedelta(hours=9))

# ========== Format ==========
# DATETIME_FORMAT is same as ISO 8601 format with Zulu(UTC) timezone.
# https://en.wikipedia.org/wiki/ISO_8601
# https://www.w3.org/TR/NOTE-datetime
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S.%f"
DATETIME_FORMAT = f"{DATE_FORMAT}T{TIME_FORMAT}Z"

# COOKIE_DATETIME_FORMAT is same as RFC 1123 format.
# https://tools.ietf.org/html/rfc1123#page-55
# https://tools.ietf.org/html/rfc2616#page-20
COOKIE_DATETIME_FORMAT = "%a, %d %b %Y %H:%M:%S GMT"

ALREADY_EXPIRED_COOKIE_DATETIME = datetime.datetime.fromtimestamp(0, tz=UTC)
NEVER_EXPIRE_COOKIE_DATETIME = datetime.datetime.fromtimestamp(stdint.INT_32_MAX, tz=UTC)
# Same with "Tue, 19 Jan 2038 03:14:07 GMT"
NEVER_EXPIRE_COOKIE_DATETIME_STR = NEVER_EXPIRE_COOKIE_DATETIME.strftime(COOKIE_DATETIME_FORMAT)
# Same with "Thu, 01 Jan 1970 00:00:00 GMT"
ALREADY_EXPIRED_COOKIE_DATETIME_STR = ALREADY_EXPIRED_COOKIE_DATETIME.strftime(COOKIE_DATETIME_FORMAT)
