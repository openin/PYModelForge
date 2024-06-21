import io
import re
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy import Integer, String, Float, DateTime


def get_column_type(col):
    type_map = {
        "integer": Integer,
        "bigint": Integer,
        "smallint": Integer,
        "varchar": String,
        "text": String,
        "float": Float,
        "real": Float,
        "numeric": Float,
        "datetime": DateTime,
        "timestamp": DateTime,
        "date": DateTime,
    }
    col_type = str(col["type"]).lower()
    for key, value in type_map.items():
        if key in col_type:
            return value
    return String


def camel_case(s):
    s = re.sub(r"([_\-])+", " ", s).title().replace(" ", "")
    return "".join([s[0].upper(), s[1:]])


def generate_model(table_name, cols, relations):
    class_name = camel_case(table_name)
    model_code = f"class {class_name}(Base):\n"
    model_code += f"    __tablename__ = '{table_name}'\n\n"

    for col in cols:
        col_name = col["name"]
        col_type = get_column_type(col)
        nullable = "" if col["nullable"] else ", nullable=False"
        pk = ", primary_key=True" if col["primary_key"] else ""
        fk = (
            f", ForeignKey('{col['foreign_key']}')"
            if col.get("foreign_key")
            else ""
        )
        model_code += (
            f"    {col_name} = Column({col_type.__name__}{nullable}{pk}{fk})\n"
        )

    model_code += "\n"
    for rel in relations:
        model_code += f"    {rel}\n"

    return model_code


def is_association_table(table_name, fks, inspector):
    if len(fks) != 2:
        return False
    pk_columns = set(
        inspector.get_pk_constraint(table_name)["constrained_columns"]
    )
    fk_columns = set(col for fk in fks for col in fk["constrained_columns"])
    return pk_columns == fk_columns


def generate_relationships(table_name, inspector):
    relations = []
    fks = inspector.get_foreign_keys(table_name)
    if is_association_table(table_name, fks, inspector):
        return []

    for fk in fks:
        parent_table = fk["referred_table"]
        constrained_columns = fk["constrained_columns"]
        parent_class = camel_case(parent_table)
        relationship_name = parent_table.lower()
        is_many_to_one = (
            len(constrained_columns) == 1
            and constrained_columns[0]
            not in inspector.get_pk_constraint(table_name)[
                "constrained_columns"
            ]
        )
        if is_many_to_one:
            relations.append(
                f"{relationship_name} = relationship('{parent_class}')"
            )
        else:
            back_populates = table_name.lower() + "s"
            relations.append(
                f"{relationship_name} = relationship('{parent_class}', back_populates='{back_populates}')"
            )

    return relations


def generate_many_to_many_relationships(inspector):
    m2m_relationships = {}
    for table in inspector.get_table_names():
        fks = inspector.get_foreign_keys(table)
        if is_association_table(table, fks, inspector):
            table1 = fks[0]["referred_table"]
            table2 = fks[1]["referred_table"]
            class1 = camel_case(table1)
            class2 = camel_case(table2)

            rel1 = f"{table2}s = relationship('{class2}', secondary='{table}', back_populates='{table1}s')"
            rel2 = f"{table1}s = relationship('{class1}', secondary='{table}', back_populates='{table2}s')"

            if table1 not in m2m_relationships:
                m2m_relationships[table1] = []
            if table2 not in m2m_relationships:
                m2m_relationships[table2] = []

            m2m_relationships[table1].append(rel1)
            m2m_relationships[table2].append(rel2)

    return m2m_relationships


def generate_models_content(inspector):
    output = io.StringIO()

    def write(text):
        output.write(text + "\n")

    write(
        "from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Table"
    )
    write("from sqlalchemy.orm import relationship")
    write("from sqlalchemy.ext.declarative import declarative_base\n")
    write("Base = declarative_base()\n")
    m2m_relationships = generate_many_to_many_relationships(inspector)

    for table in inspector.get_table_names():
        columns = inspector.get_columns(table)
        for column in columns:
            if column.get("foreign_key"):
                column["foreign_key"] = (
                    f"{column['foreign_key'].target_fullname}"
                )

        foreign_keys = inspector.get_foreign_keys(table)
        if is_association_table(table, foreign_keys, inspector):
            write(f"{table} = Table(")
            write(f"    '{table}', Base.metadata,")
            for column in columns:
                column_name = column["name"]
                column_type = get_column_type(column)
                foreign_key = (
                    f", ForeignKey('{column['foreign_key']}')"
                    if column.get("foreign_key")
                    else ""
                )
                write(
                    f"    Column('{column_name}', {column_type.__name__}{foreign_key}),"
                )
            write(")\n")
        else:
            relationships = generate_relationships(table, inspector)
            if table in m2m_relationships:
                relationships.extend(m2m_relationships[table])
            write(generate_model(table, columns, relationships))
            write("\n")
    return output.getvalue()


def output_models(content, output_file=None):
    if output_file:
        with open(output_file, "w") as f:
            f.write(content)
        print(f"Models have been written to {output_file}")
    else:
        print(content)
        print("Models have been printed to stdout", file=sys.stderr)


if __name__ == "__main__":
    db_url = "postgresql://username:password@localhost/dbname"
    engine = create_engine(db_url)
    inspect_engine = inspect(engine)
    content_for_model = generate_models_content(inspect_engine)
    output_models(content_for_model, "models.py")
