"""
Migration 0002:
- Thêm CustomerProfile.email (VARCHAR 255, nullable)
- Không unique — email chỉ để lưu thông tin liên lạc, phone mới là định danh chính
- Migrate data: copy email từ user.email sang profile.email cho các profile có user
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0001_initial'),
    ]

    operations = [
        # 1. Thêm field email
        migrations.AddField(
            model_name='customerprofile',
            name='email',
            field=models.CharField(
                max_length=255,
                blank=True,
                null=True,
                verbose_name='Email',
            ),
        ),

        # 2. Copy email từ user.email sang profile.email cho profile có user
        migrations.RunSQL(
            sql="""
                UPDATE customer_profiles
                SET email = (
                    SELECT auth_user.email
                    FROM auth_user
                    WHERE auth_user.id = customer_profiles.user_id
                      AND auth_user.email != ''
                )
                WHERE user_id IS NOT NULL;
            """,
            reverse_sql="UPDATE customer_profiles SET email = NULL;",
        ),
    ]
