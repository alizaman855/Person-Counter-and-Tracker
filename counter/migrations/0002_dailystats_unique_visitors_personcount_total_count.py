# Generated by Django 5.1.4 on 2024-12-26 06:36

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('counter', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='dailystats',
            name='unique_visitors',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='personcount',
            name='total_count',
            field=models.IntegerField(default=0),
        ),
    ]
