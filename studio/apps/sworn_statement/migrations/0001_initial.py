from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('people', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SwornStatement',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('deleted', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PersonSwornStatement',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('signed_at', models.DateTimeField(auto_now_add=True)),
                ('person', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sworn_statements',
                    to='people.person',
                )),
                ('statement', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='signers',
                    to='sworn_statement.swornstatement',
                )),
            ],
            options={
                'ordering': ['-signed_at'],
            },
        ),
    ]
