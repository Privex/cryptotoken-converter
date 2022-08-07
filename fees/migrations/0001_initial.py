# Generated by Django 2.2.23 on 2022-08-05 21:29

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('payments', '0006_coin_symbol_id_20190706_1521'),
    ]

    operations = [
        migrations.CreateModel(
            name='FeePayout',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=20, max_digits=40)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='Creation Time')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Last Update')),
                ('coin', models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to='payments.Coin')),
            ],
        ),
    ]