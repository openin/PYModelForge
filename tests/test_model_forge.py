import io
import pytest
from contextlib import redirect_stdout, redirect_stderr
from sqlalchemy import (
    create_engine,
    inspect,
    MetaData,
    Table,
    Column,
    Integer,
    String,
    ForeignKey,
)
from model_forge import (
    get_column_type,
    camel_case,
    generate_model,
    is_association_table,
    generate_relationships,
    generate_many_to_many_relationships,
    generate_models_content,
    output_models,
)


@pytest.fixture
def db_url():
    return "sqlite:///:memory:"


@pytest.fixture
def setup_database(db_url):
    engine = create_engine(db_url)
    metadata = MetaData()
    Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String),
    )
    Table(
        "posts",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String),
        Column("user_id", Integer, ForeignKey("users.id")),
    )
    Table(
        "tags",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String),
    )
    Table(
        "post_tags",
        metadata,
        Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
        Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
    )

    metadata.create_all(engine)
    connection = engine.connect()
    return connection


def test_get_column_type():
    assert get_column_type({"type": "INTEGER"}) == Integer
    assert get_column_type({"type": "VARCHAR"}) == String
    assert get_column_type({"type": "UNKNOWN"}) == String


def test_camel_case():
    assert camel_case("user_profile") == "UserProfile"
    assert camel_case("API_key") == "ApiKey"


def test_generate_model(setup_database):
    connection = setup_database
    inspector = inspect(connection)
    columns = [
        {
            "name": "id",
            "type": Integer(),
            "nullable": False,
            "primary_key": True,
        },
        {
            "name": "name",
            "type": String(),
            "nullable": False,
            "primary_key": False,
        },
    ]
    relationships = ["posts = relationship('Post', back_populates='user')"]
    model = generate_model("users", columns, relationships, inspector)
    assert "class Users(Base):" in model
    assert "__tablename__ = 'users'" in model
    assert "id = Column(Integer, nullable=False, primary_key=True)" in model
    assert "name = Column(String, nullable=False)" in model
    assert "posts = relationship('Post', back_populates='user')" in model


def test_is_association_table(setup_database):
    connection = setup_database
    inspector = inspect(connection)
    assert is_association_table(
        "post_tags", inspector.get_foreign_keys("post_tags"), inspector
    )
    assert not is_association_table(
        "users", inspector.get_foreign_keys("users"), inspector
    )


def test_generate_relationships(setup_database):
    connection = setup_database
    inspector = inspect(connection)
    relationships = generate_relationships("posts", inspector)
    assert "users = relationship('Users')" in relationships


def test_generate_many_to_many_relationships(setup_database):
    connection = setup_database
    inspector = inspect(connection)
    m2m_relationships = generate_many_to_many_relationships(inspector)
    assert "posts" in m2m_relationships
    assert "tags" in m2m_relationships
    assert any(
        "tags" in rel
        and "Tags" in rel
        and "post_tags" in rel
        and "posts" in rel
        for rel in m2m_relationships["posts"]
    )
    assert any(
        "posts" in rel
        and "Posts" in rel
        and "post_tags" in rel
        and "tags" in rel
        for rel in m2m_relationships["tags"]
    )


def test_generate_models_content(setup_database):
    connection = setup_database
    inspector = inspect(connection)
    content = generate_models_content(inspector)
    assert "class Users(Base):" in content
    assert "class Posts(Base):" in content
    assert "class Tags(Base):" in content
    assert "post_tags = Table(" in content


def test_output_models_to_stdout(setup_database):
    output = io.StringIO()
    stderr = io.StringIO()
    connection = setup_database
    inspector = inspect(connection)
    content = generate_models_content(inspector)

    with redirect_stdout(output), redirect_stderr(stderr):
        output_models(content)

    stdout_content = output.getvalue()
    stderr_content = stderr.getvalue()

    assert "class Users(Base):" in stdout_content
    assert "class Posts(Base):" in stdout_content
    assert "class Tags(Base):" in stdout_content
    assert "post_tags = Table(" in stdout_content
    assert "Models have been printed to stdout" in stderr_content


if __name__ == "__main__":
    pytest.main()
