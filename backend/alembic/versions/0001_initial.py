"""Initial schema; immutable table definitions captured in this revision."""
from alembic import op
import sqlalchemy as sa

revision='0001'
down_revision=None
branch_labels=None
depends_on=None


def upgrade():
    # The initial release schema is frozen separately from application models.
    from pathlib import Path
    import json
    schema=json.loads((Path(__file__).parent/'0001_schema.json').read_text())
    for table in schema:
        columns=[]
        for c in table['columns']:
            types={'string':sa.String,'integer':sa.Integer,'float':sa.Float,'json':sa.JSON,'datetime':lambda:sa.DateTime(timezone=True)}
            typ=types[c['type']](c['length']) if c.get('length') else types[c['type']]()
            args=[sa.ForeignKey(c['foreign_key'],ondelete=c.get('ondelete'))] if c.get('foreign_key') else []
            columns.append(sa.Column(c['name'],typ,*args,primary_key=c['primary_key'],nullable=c['nullable']))
        constraints=[sa.UniqueConstraint(*u) for u in table['unique']]
        op.create_table(table['name'],*columns,*constraints)
        for i in table['indexes']: op.create_index(i['name'],table['name'],i['columns'],unique=i['unique'])


def downgrade():
    from pathlib import Path
    import json
    schema=json.loads((Path(__file__).parent/'0001_schema.json').read_text())
    for table in reversed(schema): op.drop_table(table['name'])
