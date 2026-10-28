from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Holiday',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=100)),
                ('date', models.DateField()),
                ('deleted', models.DateField(blank=True, null=True)),
            ],
            options={
                'ordering': ['date'],
            },
        ),
    ]
