from __future__ import annotations

import re

import fastapi.responses
import psycopg.errors as pg_exc
import sqlalchemy.exc as sa_exc

import app.const.error as error_const
import app.db.__mixin__ as db_mixin
import app.error_handler.__type__ as err_type

IntegrityErrorMsgMap: dict[db_mixin.NCKey, str] = {
    "ix": error_const.CommonErrorMsg.DB_INTEGRITY_CONSTRAINT_ERROR,
    "uq": error_const.CommonErrorMsg.DB_UNIQUE_CONSTRAINT_ERROR,
    "ck": error_const.CommonErrorMsg.DB_CHECK_CONSTRAINT_ERROR,
    "fk": error_const.CommonErrorMsg.DB_FOREIGN_KEY_CONSTRAINT_ERROR,
    "pk": error_const.CommonErrorMsg.DB_NOT_NULL_CONSTRAINT_ERROR,
}


def error_to_nckey(msg_primary: str) -> tuple[db_mixin.NCKey, re.Match] | None:
    if not isinstance(msg_primary, str):
        return None
    for nckey, ncdef in db_mixin.NAMING_CONVENTION_DICT.items():
        if matched_info := ncdef.regex.match(msg_primary):
            return nckey, matched_info
    return None


async def psycopg_dataerror_handler(req: err_type.ReqType, err: pg_exc.DataError) -> err_type.RespType:
    # TODO: FIXME: THis sould be handled by CRUDBase or CRUDView.
    # [print(attr, getattr(err.diag, attr)) for attr in dir(err.diag) if not attr.startswith("_")]
    status_code = fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY
    content = [error_const.ServerError.DB_DATA_ERROR.value.model_dump()]
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


async def psycopg_integrityerror_handler(req: err_type.ReqType, err: pg_exc.IntegrityError) -> err_type.RespType:
    # TODO: FIXME: THis sould be handled by CRUDBase or CRUDView.
    match err:
        case pg_exc.IntegrityConstraintViolation():
            parsed_error = error_const.ServerError.DB_INTEGRITY_CONSTRAINT_ERROR.value
        case pg_exc.RestrictViolation():
            err_msg = error_const.CommonErrorMsg.DB_RESTRICT_CONSTRAINT_ERROR
            parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)
        case pg_exc.NotNullViolation():
            err_msg = error_const.CommonErrorMsg.DB_NOT_NULL_CONSTRAINT_ERROR
            parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)
        case pg_exc.ForeignKeyViolation():
            err_msg = error_const.CommonErrorMsg.DB_FOREIGN_KEY_CONSTRAINT_ERROR
            err_msg = err_msg.format(referred_table_name=err.diag.table_name or "")
            parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)
        case pg_exc.UniqueViolation():
            err_msg = error_const.CommonErrorMsg.DB_UNIQUE_CONSTRAINT_ERROR
            parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)
        case pg_exc.CheckViolation():
            err_msg = error_const.CommonErrorMsg.DB_CHECK_CONSTRAINT_ERROR
            parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)
        case pg_exc.ExclusionViolation():
            err_msg = error_const.CommonErrorMsg.DB_EXCLUSION_CONSTRAINT_ERROR
            parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)
        case _:
            parsed_error = error_const.ServerError.DB_UNKNOWN_ERROR.value
            if nc_extract := error_to_nckey(err.diag.message_primary):
                nc_key, _ = nc_extract
                err_msg = IntegrityErrorMsgMap.get(nc_key, error_const.ServerError.DB_UNKNOWN_ERROR.value)
                parsed_error = error_const.ErrorStruct.value_error(msg=err_msg)

    return fastapi.responses.JSONResponse(
        status_code=fastapi.status.HTTP_422_UNPROCESSABLE_ENTITY, content=[parsed_error.model_dump()]
    )


async def psycopg_databaseerror_handler(req: err_type.ReqType, err: pg_exc.DatabaseError) -> err_type.RespType:
    if handler_func := error_handler_patterns.get(type(err)):
        return await handler_func(req, err)

    status_code = fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    content = [error_const.ServerError.DB_UNKNOWN_ERROR.value.model_dump()]
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


async def psycopg_connectionerror_handler(req: err_type.ReqType, err: pg_exc.Error) -> err_type.RespType:
    status_code = fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    content = [error_const.ServerError.DB_CONNECTION_ERROR.value.model_dump()]
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


async def psycopg_criticalerror_handler(req: err_type.ReqType, err: pg_exc.Error) -> err_type.RespType:
    status_code = fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    content = [error_const.ServerError.DB_CRITICAL_ERROR.value.model_dump()]
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


async def sqlalchemy_error_handler(req: err_type.ReqType, err: sa_exc.SQLAlchemyError) -> err_type.RespType:
    orig_exception: pg_exc.Error | BaseException | None = getattr(err, "orig", None)  # For sa_exc.IntegrityError
    pg_exc.InvalidTextRepresentation
    if orig_exception:
        for orig_err_type in type(orig_exception).__mro__:
            if handler_func := error_handler_patterns.get(orig_err_type):
                return await handler_func(req, orig_exception)

    status_code = fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR
    content = [error_const.ServerError.DB_UNKNOWN_ERROR.value.model_dump()]
    return fastapi.responses.JSONResponse(status_code=status_code, content=content)


error_handler_patterns = {
    # PostgreSQL Connection Error
    pg_exc.InterfaceError: psycopg_connectionerror_handler,
    pg_exc.CannotConnectNow: psycopg_connectionerror_handler,
    # PostgreSQL Critical Error
    pg_exc.DataCorrupted: psycopg_criticalerror_handler,
    pg_exc.IndexCorrupted: psycopg_criticalerror_handler,
    pg_exc.DiskFull: psycopg_criticalerror_handler,
    pg_exc.OutOfMemory: psycopg_criticalerror_handler,
    pg_exc.TooManyArguments: psycopg_criticalerror_handler,
    pg_exc.TooManyColumns: psycopg_criticalerror_handler,
    pg_exc.ConfigFileError: psycopg_criticalerror_handler,
    pg_exc.InvalidPassword: psycopg_criticalerror_handler,
    pg_exc.AdminShutdown: psycopg_criticalerror_handler,
    pg_exc.CrashShutdown: psycopg_criticalerror_handler,
    pg_exc.DatabaseDropped: psycopg_criticalerror_handler,
    pg_exc.SystemError: psycopg_criticalerror_handler,
    pg_exc.IoError: psycopg_criticalerror_handler,
    pg_exc.UndefinedFile: psycopg_criticalerror_handler,
    pg_exc.DuplicateFile: psycopg_criticalerror_handler,
    # PostgreSQL Integrity Error
    pg_exc.IntegrityConstraintViolation: psycopg_integrityerror_handler,
    pg_exc.RestrictViolation: psycopg_integrityerror_handler,
    pg_exc.NotNullViolation: psycopg_integrityerror_handler,
    pg_exc.ForeignKeyViolation: psycopg_integrityerror_handler,
    pg_exc.UniqueViolation: psycopg_integrityerror_handler,
    pg_exc.CheckViolation: psycopg_integrityerror_handler,
    pg_exc.ExclusionViolation: psycopg_integrityerror_handler,
    # PostgreSQL Data Error
    pg_exc.DataError: psycopg_dataerror_handler,
    # PostgreSQL Database Error
    pg_exc.Error: psycopg_databaseerror_handler,
    # SQLAlchemy Error
    sa_exc.SQLAlchemyError: sqlalchemy_error_handler,
}