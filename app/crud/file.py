import app.crud.__interface__ as crud_interface
import app.db.model.file as file_model
import app.schema.file as file_schema

fileCRUD = crud_interface.CRUDBase[
    file_model.File,
    file_schema.FileCreate,
    file_schema.FileUpdate,
](model=file_model.File)
