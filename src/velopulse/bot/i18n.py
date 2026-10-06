# ruff: noqa: RUF001
"""Localization dictionaries and helpers for English and Russian languages."""

from typing import Any

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # Start & Language
        "select_language": "Please select your language:",
        "btn_lang_en": "🇬🇧 English",
        "btn_lang_ru": "🇷🇺 Russian",
        "greeting": (
            "Hello, {first_name}! Welcome to VeloPulse.\nLet's set up your profile to get started."
        ),
        "btn_profile": "👤 Profile",
        "profile_not_setup": (
            "Your profile is not set up yet. Please complete the profile setup to continue."
        ),
        # Profile Menu
        "profile_menu_title": (
            "👤 <b>Profile Setup & Management</b>\n\n"
            "Manage your connected services, bikes, and settings below:"
        ),
        "btn_new_trip": "🚴 New Trip",
        "btn_strava": "🔗 Strava",
        "btn_bikes": "🚲 Bikes",
        "btn_settings": "⚙️ Settings",
        "btn_clean_chat": "🧹 Clean chat",
        "btn_back": "◀️ Back",
        "btn_cancel": "❌ Cancel",
        # Strava
        "strava_title": (
            "🔴🔴 <b>Strava connectivity is not yet ready. Please use the 'New Trip' button in your profile to add trips manually!</b> 🔴🔴\n\n"
            "🔗 <b>Strava Integration</b>\n\n"
            "{status_text}\n\n"
            "Connect your Strava account to automatically sync activities, track gear distance, "
            "and receive real-time wear alerts.\n\n"
            "1. Authorize via Strava: <a href='{auth_url}'>Connect Strava</a>\n"
            "2. Or link via deep-link: <code>/start &lt;your_user_id&gt;</code>"
        ),
        "strava_connected": "Status: 🟢 <b>Connected</b> (Athlete ID: {athlete_id})",
        "strava_not_connected": "Status: ⚪ <b>Not connected</b>",
        # Bikes Menu
        "bikes_intro": (
            "You can add up to 3 bikes.\nSelect a bike to manage it or create a new one."
        ),
        "btn_create_bike": "➕ Create bike",
        "bike_item_btn": "🚲 {name}",
        # Create Bike Flow
        "step_bike_type": "What type of bike is it?",
        "btn_road": "🛣️🚴 Road bike",
        "btn_gravel": "🪨🚴 Gravel bike",
        "btn_mtb": "⛰️🚵 MTB bike",
        "step_bike_model": ("What is the bike model?\nExample: Trek Domane AL 5"),
        "step_bike_model_road": (
            "🛣️🚴 What is the model of your road bike?\nExample: Trek Domane AL 5"
        ),
        "step_bike_model_gravel": (
            "🪨🚴 What is the model of your gravel bike?\nExample: Trek Checkpoint ALR 5"
        ),
        "step_bike_model_mtb": ("⛰️🚵 What is the model of your MTB?\nExample: Trek Marlin 7"),
        "err_invalid_model": "Please enter a non-empty bike model name.",
        # Mileage Steps
        "step_cassette_mileage": (
            "⚙️ What is the current mileage of the rear cassette in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "step_chain_mileage": (
            "⛓️ What is the current mileage of the chain in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "step_chain_lube_mileage": (
            "⛓️ How many kilometers ago was the chain last lubricated?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 50):"
        ),
        "step_front_tire_mileage": (
            "🛞 What is the current mileage of the front tire in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "step_rear_tire_mileage": (
            "🛞 What is the current mileage of the rear tire in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "step_front_brake_type": "🛑 What type of front brake do you have?",
        "step_front_brake_mileage": (
            "🛑 What is the current mileage of the front brake in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "step_rear_brake_type": "🛑 What type of rear brake do you have?",
        "step_rear_brake_mileage": (
            "🛑 What is the current mileage of the rear brake in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "step_suspension_mileage": (
            "🛠️ What is the current mileage of the suspension fork in km?\n\n"
            "💡 Choose a preset button below or send your exact mileage directly in the chat (e.g. 1250):"
        ),
        "btn_disc_brake": "💿 Disc brake",
        "btn_rim_brake": "🛞 Rim brake",
        "err_invalid_mileage": (
            "Please enter a valid non-negative number for mileage in km, or select a preset button below."
        ),
        "mileage_prompt_hint": "Select a preset or enter exact mileage in km:",
        # Confirmation & Bike Management
        "bike_created_success": "Your bike has been created successfully! 🚲",
        "bike_manage_title": (
            "🚲 <b>{name}</b> ({bike_type})\nSelect a component to inspect or perform maintenance:"
        ),
        "btn_comp_chain": "⛓️ Chain",
        "btn_comp_cassette": "⚙️ Cassette",
        "btn_comp_front_tire": "🛞 Front tire",
        "btn_comp_rear_tire": "🛞 Rear tire",
        "btn_comp_front_brake": "🛑 Front brake",
        "btn_comp_rear_brake": "🛑 Rear brake",
        "btn_comp_suspension": "🛠️ Suspension fork",
        "btn_delete_bike": "🗑️ Delete bike",
        # Component Details
        "comp_details_template": (
            "{icon} <b>{comp_name}</b>\n\n"
            "Current mileage: <b>{current_km:,.1f} km</b>\n"
            "Estimated service life: <b>{lifespan_km:,.1f} km</b>\n"
            "Usage: <b>{pct:.0f}%</b>\n\n"
            "{bar}\n\n"
            "{lube_line}"
            "Status: {status_badge}"
        ),
        "lube_due_in": "Lubrication: <b>Due in {due_km} km</b>\n",
        "lube_due_now": "Lubrication: <b>🔴 Due now (Lubricate chain)</b>\n",
        "status_good": "✅ Good",
        "status_soon": "⚠️ Service soon",
        "status_replace": "🔴 Replacement recommended",
        "btn_replace_comp": "🔄 Replace component",
        # Component Replacement Flow
        "replace_comp_prompt": (
            "Are you sure you want to replace this component?\nThis will reset its mileage to 0 km."
        ),
        "btn_yes_replace": "✅ Yes, replace",
        "comp_replaced_success": "Component has been successfully replaced! 🔄",
        # Delete Bike Flow
        "delete_bike_prompt": (
            "Are you sure you want to delete <b>{bike_name}</b>?\n"
            "All components and maintenance history for this bike will be permanently deleted."
        ),
        "btn_yes_delete": "✅ Yes, delete",
        "bike_deleted_success": "Bike has been deleted.",
        # Settings & Delete Account
        "settings_title": "⚙️ <b>Settings</b>\n\nSelect an option below:",
        "btn_language": "🌐 Language",
        "lang_changed": "Language changed to English 🇬🇧",
        "btn_delete_account": "🗑️ Delete account",
        "delete_account_prompt": (
            "Are you sure you want to delete your account?\n"
            "This action cannot be undone. All your bikes, components, and data will be permanently deleted."
        ),
        "btn_yes_delete_account": "✅ Yes, delete",
        "btn_no_keep_account": "❌ No, keep",
        "account_deleted_farewell": (
            "Your account has been deleted.\n"
            "If you want to use VeloPulse again, send /start anytime."
        ),
        # Manual Trip
        "trip_no_bikes": (
            "You don't have any bikes yet.\n"
            "Please create a bike first in 🚲 Bikes to record a trip."
        ),
        "trip_select_bike": "🚴 <b>Select the bike you used for this trip:</b>",
        "trip_enter_distance": (
            "🛣️ <b>How many kilometers was your trip?</b>\n\n"
            "💡 Send the distance in km directly in chat (e.g. <code>45.5</code> or <code>60</code>):"
        ),
        "trip_enter_elevation": (
            "⛰️ <b>What was the total elevation gain in meters?</b>\n\n"
            "💡 Select a preset below or send the exact elevation in meters (e.g. <code>350</code>):"
        ),
        "trip_invalid_distance": "Please enter a valid positive number for distance in km (e.g. 45.5):",
        "trip_invalid_elevation": "Please enter a valid non-negative number for elevation in meters (e.g. 350):",
        "trip_success": (
            "🎉 <b>Great ride, {first_name}! Hope you enjoyed the trip!</b> 🚴💨\n\n"
            "📊 <b>Trip Summary:</b>\n"
            "🚲 Bike: <b>{bike_name}</b>\n"
            "🛣️ Distance: <b>{dist:,.1f} km</b>\n"
            "⛰️ Elevation: <b>{elev:,.0f} m</b>\n\n"
            "⚙️ Component wear and mileage updated successfully! 🔧"
        ),
        "chat_cleaned": "Chat history cleaned. 🧹",
        # Unexpected message fallback
        "unexpected_action": "Please use the buttons below to proceed.",
        # Maintenance Service Wizard
        "service_start": "🔧 <b>Maintenance Service Logging</b>\n\nSelect a bicycle to log maintenance:",
        "service_no_bikes": "You don't have any registered bicycles yet. Add a bike first to log maintenance.",
        "service_select_component": "Select the component you serviced on <b>{bike_name}</b>:",
        "service_no_components": "No active components found on this bike.",
        "service_select_type": "Select the type of maintenance performed on <b>{component_name}</b>:",
        "service_enter_notes": "📝 Enter technician notes or service description (or tap Skip):",
        "service_enter_cost": "💰 Enter the cost in your currency (e.g. <code>25.50</code>, or tap Free):",
        "service_invalid_cost": "⚠️ Invalid amount. Please enter a positive number (e.g. <code>15.00</code>) or tap Free:",
        "service_success": (
            "✅ <b>Maintenance Logged Successfully!</b>\n\n"
            "🚲 <b>Bike:</b> {bike_name}\n"
            "🔩 <b>Component:</b> {component_name}\n"
            "🔧 <b>Action:</b> {action}\n"
            "📝 <b>Notes:</b> {notes}\n"
            "💰 <b>Cost:</b> {cost}\n"
            "⏱️ <b>Odometer:</b> {odometer_km} km"
        ),
        "service_replace_success": (
            "🔄 <b>Component Replaced & Reset!</b>\n\n"
            "🚲 <b>Bike:</b> {bike_name}\n"
            "🔩 <b>Old part retired:</b> {old_name}\n"
            "🆕 <b>New part installed:</b> {new_name}\n"
            "📊 <b>Wear:</b> Reset to 0.00 WP\n"
            "💰 <b>Cost:</b> {cost}"
        ),
        "service_cancelled": "❌ Maintenance logging cancelled.",
        "btn_service_lube": "🧼 Clean & Lube",
        "btn_service_inspect": "🔧 Inspect & Tune",
        "btn_service_repair": "🛠️ Repair",
        "btn_service_replace": "🔄 Replace Part",
        "btn_service_season": "📅 Season Prep",
        "btn_skip_notes": "⏭️ Skip notes",
        "btn_skip_cost": "0 💵 (Free / No cost)",
        "service_notes_skipped": "None",
    },
    "ru": {
        # Start & Language
        "select_language": "Пожалуйста, выберите язык:",
        "btn_lang_en": "🇬🇧 English",
        "btn_lang_ru": "🇷🇺 Russian",
        "greeting": (
            "Привет, {first_name}! Добро пожаловать в VeloPulse.\n"
            "Давайте настроим ваш профиль, чтобы начать."
        ),
        "btn_profile": "👤 Профиль",
        "profile_not_setup": (
            "Ваш профиль ещё не настроен. Пожалуйста, завершите настройку профиля, чтобы продолжить."
        ),
        # Profile Menu
        "profile_menu_title": (
            "👤 <b>Настройка профиля и управление</b>\n\n"
            "Управляйте интеграцией со Strava, велосипедами и настройками:"
        ),
        "btn_new_trip": "🚴 Новая поездка",
        "btn_strava": "🔗 Strava",
        "btn_bikes": "🚲 Велосипеды",
        "btn_settings": "⚙️ Настройки",
        "btn_clean_chat": "🧹 Очистить чат",
        "btn_back": "◀️ Назад",
        "btn_cancel": "❌ Отмена",
        # Strava
        "strava_title": (
            "🔴🔴 <b>Подключение Strava пока не готово. Пожалуйста, используйте кнопку «Новая поездка» в профиле, чтобы добавить поездку вручную!</b> 🔴🔴\n\n"
            "🔗 <b>Интеграция со Strava</b>\n\n"
            "{status_text}\n\n"
            "Подключите ваш аккаунт Strava для автоматической синхронизации поездок, учёта износа "
            "и своевременных оповещений.\n\n"
            "1. Авторизуйтесь через Strava: <a href='{auth_url}'>Подключить Strava</a>\n"
            "2. Или свяжите через deep-link: <code>/start &lt;ваш_user_id&gt;</code>"
        ),
        "strava_connected": "Статус: 🟢 <b>Подключено</b> (Athlete ID: {athlete_id})",
        "strava_not_connected": "Статус: ⚪ <b>Не подключено</b>",
        # Bikes Menu
        "bikes_intro": (
            "Вы можете добавить до 3 велосипедов.\n"
            "Выберите велосипед для управления или создайте новый."
        ),
        "btn_create_bike": "➕ Создать велосипед",
        "bike_item_btn": "🚲 {name}",
        # Create Bike Flow
        "step_bike_type": "Какой это тип велосипеда?",
        "btn_road": "🛣️🚴 Road bike",
        "btn_gravel": "🪨🚴 Gravel bike",
        "btn_mtb": "⛰️🚵 MTB bike",
        "step_bike_model": ("Какая модель велосипеда?\nНапример: Trek Domane AL 5"),
        "step_bike_model_road": ("🛣️🚴 Какая модель твоего шоссейника?\nНапример: Trek Domane AL 5"),
        "step_bike_model_gravel": (
            "🪨🚴 Какая модель твоего гравела?\nНапример: Trek Checkpoint ALR 5"
        ),
        "step_bike_model_mtb": ("⛰️🚵 Какая модель твоего МТБ?\nНапример: Trek Marlin 7"),
        "err_invalid_model": "Пожалуйста, введите непустое название модели велосипеда.",
        # Mileage Steps
        "step_cassette_mileage": (
            "⚙️ Какой текущий пробег задней кассеты в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "step_chain_mileage": (
            "⛓️ Какой текущий пробег цепи в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "step_chain_lube_mileage": (
            "⛓️ Сколько километров назад смазывалась цепь?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 50):"
        ),
        "step_front_tire_mileage": (
            "🛞 Какой текущий пробег передней покрышки в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "step_rear_tire_mileage": (
            "🛞 Какой текущий пробег задней покрышки в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "step_front_brake_type": "🛑 Какой тип переднего тормоза?",
        "step_front_brake_mileage": (
            "🛑 Какой текущий пробег переднего тормоза в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "step_rear_brake_type": "🛑 Какой тип заднего тормоза?",
        "step_rear_brake_mileage": (
            "🛑 Какой текущий пробег заднего тормоза в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "step_suspension_mileage": (
            "🛠️ Какой текущий пробег вилки амортизатора в км?\n\n"
            "💡 Выберите готовое значение на кнопках ниже или отправьте точный пробег сообщением в чат (например: 1250):"
        ),
        "btn_disc_brake": "💿 Дисковый",
        "btn_rim_brake": "🛞 Ободной",
        "err_invalid_mileage": (
            "Пожалуйста, введите корректное неотрицательное число пробега в км или выберите кнопку ниже."
        ),
        "mileage_prompt_hint": "Выберите готовое значение или отправьте точный пробег в км:",
        # Confirmation & Bike Management
        "bike_created_success": "Ваш велосипед успешно создан! 🚲",
        "bike_manage_title": (
            "🚲 <b>{name}</b> ({bike_type})\nВыберите компонент для просмотра или обслуживания:"
        ),
        "btn_comp_chain": "⛓️ Цепь",
        "btn_comp_cassette": "⚙️ Кассета",
        "btn_comp_front_tire": "🛞 Передняя покрышка",
        "btn_comp_rear_tire": "🛞 Задняя покрышка",
        "btn_comp_front_brake": "🛑 Передний тормоз",
        "btn_comp_rear_brake": "🛑 Задний тормоз",
        "btn_comp_suspension": "🛠️ Вилка амортизатора",
        "btn_delete_bike": "🗑️ Удалить велосипед",
        # Component Details
        "comp_details_template": (
            "{icon} <b>{comp_name}</b>\n\n"
            "Текущий пробег: <b>{current_km:,.1f} км</b>\n"
            "Расчётный ресурс: <b>{lifespan_km:,.1f} км</b>\n"
            "Износ: <b>{pct:.0f}%</b>\n\n"
            "{bar}\n\n"
            "{lube_line}"
            "Статус: {status_badge}"
        ),
        "lube_due_in": "Смазка: <b>Через {due_km} км</b>\n",
        "lube_due_now": "Смазка: <b>🔴 Срочно (Смажьте цепь)</b>\n",
        "status_good": "✅ В норме",
        "status_soon": "⚠️ Скоро потребуется обслуживание",
        "status_replace": "🔴 Рекомендуется замена",
        "btn_replace_comp": "🔄 Заменить компонент",
        # Component Replacement Flow
        "replace_comp_prompt": (
            "Вы уверены, что хотите заменить этот компонент?\nПробег будет сброшен до 0 км."
        ),
        "btn_yes_replace": "✅ Да, заменить",
        "comp_replaced_success": "Компонент успешно заменён! 🔄",
        # Delete Bike Flow
        "delete_bike_prompt": (
            "Вы уверены, что хотите удалить <b>{bike_name}</b>?\n"
            "Все компоненты и история обслуживания этого велосипеда будут удалены навсегда."
        ),
        "btn_yes_delete": "✅ Да, удалить",
        "bike_deleted_success": "Велосипед удалён.",
        # Settings & Delete Account
        "settings_title": "⚙️ <b>Настройки</b>\n\nВыберите пункт меню:",
        "btn_language": "🌐 Язык",
        "lang_changed": "Язык изменён на Русский 🇷🇺",
        "btn_delete_account": "🗑️ Удалить аккаунт",
        "delete_account_prompt": (
            "Вы уверены, что хотите удалить свой аккаунт?\n"
            "Это действие нельзя отменить. Все ваши велосипеды, компоненты и данные будут удалены навсегда."
        ),
        "btn_yes_delete_account": "✅ Да, удалить",
        "btn_no_keep_account": "❌ Нет, оставить",
        "account_deleted_farewell": (
            "Ваш аккаунт удалён.\n"
            "Если вы захотите снова использовать VeloPulse, отправьте /start в любое время."
        ),
        # Manual Trip
        "trip_no_bikes": (
            "У вас пока нет велосипедов.\n"
            "Сначала добавьте велосипед в разделе 🚲 Велосипеды, чтобы записать поездку."
        ),
        "trip_select_bike": "🚴 <b>Выберите велосипед, на котором была поездка:</b>",
        "trip_enter_distance": (
            "🛣️ <b>Сколько километров длилась ваша поездка?</b>\n\n"
            "💡 Отправьте расстояние в км сообщением в чат (например: <code>45.5</code> или <code>60</code>):"
        ),
        "trip_enter_elevation": (
            "⛰️ <b>Какой был общий набор высоты в метрах?</b>\n\n"
            "💡 Выберите готовое значение ниже или отправьте число в метрах (например: <code>350</code>):"
        ),
        "trip_invalid_distance": "Пожалуйста, введите положительное число расстояния в км (например: 45.5):",
        "trip_invalid_elevation": "Пожалуйста, введите корректное число набора высоты в метрах (например: 350):",
        "trip_success": (
            "🎉 <b>Отличная поездка, {first_name}! Надеемся, поездка прошла с удовольствием!</b> 🚴💨\n\n"
            "📊 <b>Итоги поездки:</b>\n"
            "🚲 Велосипед: <b>{bike_name}</b>\n"
            "🛣️ Дистанция: <b>{dist:,.1f} км</b>\n"
            "⛰️ Набор высоты: <b>{elev:,.0f} м</b>\n\n"
            "⚙️ Пробег и износ компонентов успешно обновлены! 🔧"
        ),
        "chat_cleaned": "История чата очищена. 🧹",
        # Unexpected message fallback
        "unexpected_action": "Пожалуйста, используйте кнопки ниже для продолжения.",
        # Maintenance Service Wizard
        "service_start": "🔧 <b>Журнал технического обслуживания</b>\n\nВыберите велосипед для регистрации обслуживания:",
        "service_no_bikes": "У вас пока нет зарегистрированных велосипедов. Сначала добавьте велосипед.",
        "service_select_component": "Выберите обслуженный компонент на <b>{bike_name}</b>:",
        "service_no_components": "На этом велосипеде не найдено активных компонентов.",
        "service_select_type": "Выберите тип выполненного обслуживания для <b>{component_name}</b>:",
        "service_enter_notes": "📝 Введите заметки или описание работ (или нажмите Пропустить):",
        "service_enter_cost": "💰 Введите стоимость обслуживания (например <code>25.50</code>, или нажмите Бесплатно):",
        "service_invalid_cost": "⚠️ Некорректная сумма. Пожалуйста, введите положительное число (например <code>15.00</code>) или нажмите Бесплатно:",
        "service_success": (
            "✅ <b>Обслуживание успешно записано!</b>\n\n"
            "🚲 <b>Велосипед:</b> {bike_name}\n"
            "🔩 <b>Компонент:</b> {component_name}\n"
            "🔧 <b>Действие:</b> {action}\n"
            "📝 <b>Заметки:</b> {notes}\n"
            "💰 <b>Стоимость:</b> {cost}\n"
            "⏱️ <b>Одометр:</b> {odometer_km} км"
        ),
        "service_replace_success": (
            "🔄 <b>Компонент заменен и сброшен!</b>\n\n"
            "🚲 <b>Велосипед:</b> {bike_name}\n"
            "🔩 <b>Старая деталь отправлена в архив:</b> {old_name}\n"
            "🆕 <b>Новая деталь установлена:</b> {new_name}\n"
            "📊 <b>Износ:</b> Сброшен на 0.00 WP\n"
            "💰 <b>Стоимость:</b> {cost}"
        ),
        "service_cancelled": "❌ Регистрация обслуживания отменена.",
        "btn_service_lube": "🧼 Чистка и смазка",
        "btn_service_inspect": "🔧 Осмотр и настройка",
        "btn_service_repair": "🛠️ Ремонт",
        "btn_service_replace": "🔄 Замена детали",
        "btn_service_season": "📅 Подготовка к сезону",
        "btn_skip_notes": "⏭️ Пропустить заметки",
        "btn_skip_cost": "0 💵 (Бесплатно)",
        "service_notes_skipped": "Нет",
    },
}


def t(key: str, lang: str = "en", **kwargs: Any) -> str:
    """Get localized string by key and language code."""
    loc = MESSAGES.get(lang) or MESSAGES["en"]
    template = loc.get(key) or MESSAGES["en"].get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template
