# Generated by Django 5.0.6 on 2024-06-25 19:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0003_alter_profile_options"),
    ]

    operations = [
        migrations.AlterField(
            model_name="landingjob",
            name="unsorted_revisions",
            field=models.ManyToManyField(
                related_name="landing_jobs",
                through="main.RevisionLandingJob",
                to="main.revision",
            ),
        ),
    ]
