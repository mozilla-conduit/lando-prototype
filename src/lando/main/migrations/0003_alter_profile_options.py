# Generated by Django 5.0.6 on 2024-06-03 18:44

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0002_profile"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="profile",
            options={
                "permissions": (
                    ("scm_conduit", "SCM_CONDUIT"),
                    ("scm_level_1", "SCM_LEVEL_1"),
                    ("scm_level_2", "SCM_LEVEL_2"),
                    ("scm_level_3", "SCM_LEVEL_3"),
                    ("scm_versioncontrol", "SCM_VERSIONCONTROL"),
                )
            },
        ),
    ]
