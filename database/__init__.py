# database/__init__.py
from .connection import get_pool, init_db, set_database_timezone, update_old_records_timezone, DAMASCUS_TZ, format_local_time
from .core import get_bot_status, set_bot_status, get_maintenance_message, get_exchange_rate, set_exchange_rate, get_syriatel_numbers, set_syriatel_numbers
from .users import get_user_profile, get_user_full_stats, get_user_by_id, update_user_balance, get_all_users, is_admin_user
from .referrals import generate_referral_code, check_duplicate_referral, process_referral, get_referral_stats, detect_suspicious_referrals, get_user_referral_info
from .products import get_app_variants, get_app_variant, delete_app_variant, get_product_options, get_product_option, update_product_option, add_product_option, get_product_options_cached, get_all_applications, get_applications_by_category, get_all_categories, update_category, get_category_by_id, delete_category, reorder_categories, add_category
from .orders import create_deposit_request, create_order, create_order_with_variant, update_order_group_message, update_deposit_group_message
from .points import get_user_points, get_points_history, add_points_history, create_redemption_request, approve_redemption, reject_redemption, calculate_points_value, add_points, deduct_points, get_points_per_order, get_points_per_deposit, get_points_per_referral, get_user_points_summary, get_total_points_redeemed, get_redemption_rate
from .admin import get_all_admins, add_admin, remove_admin, get_admin_info, get_admin_logs, fix_manual_vip_for_existing_users
from .stats import get_bot_stats, get_top_users_by_deposits, get_top_users_by_orders, get_top_users_by_referrals, get_top_users_by_points, get_report_settings, update_report_setting
from .vip import get_vip_levels, get_user_vip, update_user_vip, get_next_vip_level
from .cache_utils import invalidate_user_cache, invalidate_exchange_rate, invalidate_categories

__all__ = [
    'get_pool', 'init_db', 'set_database_timezone', 'update_old_records_timezone', 'DAMASCUS_TZ', 'format_local_time',
    'get_bot_status', 'set_bot_status', 'get_maintenance_message', 'get_exchange_rate', 'set_exchange_rate', 'get_syriatel_numbers', 'set_syriatel_numbers',
    'get_user_profile', 'get_user_full_stats', 'get_user_by_id', 'update_user_balance', 'get_all_users', 'is_admin_user',
    'generate_referral_code', 'check_duplicate_referral', 'process_referral', 'get_referral_stats', 'detect_suspicious_referrals', 'get_user_referral_info',
    'get_app_variants', 'get_app_variant', 'delete_app_variant', 'get_product_options', 'get_product_option', 'update_product_option', 'add_product_option', 'get_product_options_cached', 'get_all_applications', 'get_applications_by_category', 'get_all_categories', 'update_category', 'get_category_by_id', 'delete_category', 'reorder_categories', 'add_category',
    'create_deposit_request', 'create_order', 'create_order_with_variant', 'update_order_group_message', 'update_deposit_group_message',
    'get_user_points', 'get_points_history', 'add_points_history', 'create_redemption_request', 'approve_redemption', 'reject_redemption', 'calculate_points_value', 'add_points', 'deduct_points', 'get_points_per_order', 'get_points_per_deposit', 'get_points_per_referral', 'get_user_points_summary', 'get_total_points_redeemed', 'get_redemption_rate',
    'get_all_admins', 'add_admin', 'remove_admin', 'get_admin_info', 'get_admin_logs', 'fix_manual_vip_for_existing_users',
    'get_bot_stats', 'get_top_users_by_deposits', 'get_top_users_by_orders', 'get_top_users_by_referrals', 'get_top_users_by_points', 'get_report_settings', 'update_report_setting',
    'get_vip_levels', 'get_user_vip', 'update_user_vip', 'get_next_vip_level',
    'invalidate_user_cache', 'invalidate_exchange_rate', 'invalidate_categories'
]