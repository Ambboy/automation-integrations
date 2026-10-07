"""Add ETM order workflows without replacing concurrent service additions."""
import hashlib
import json
from pathlib import Path

from automation_integrations.etm_document import supplement


ROOT = Path(__file__).resolve().parents[1]


def update(root=ROOT):
    registry = root / 'registry'
    contract_path = registry / 'contracts/etm.json'
    contract = json.loads(contract_path.read_text())
    supplement(contract['operations']['invoice_create'])
    pdf = root / 'docs/etm-order-research/ETM_Order_24_01_25.pdf'
    source = {'local_snapshot': str(pdf.relative_to(root)),
              'title': 'ETM API. Работа с заказами, 24.01.2025',
              'sha256': hashlib.sha256(pdf.read_bytes()).hexdigest(),
              'provenance': 'Vendor-authored order manual retained by the existing ETM integration; '
                            'cross-checked with live OpenAPI and previous provider readbacks.'}
    contract['operations']['invoice_create']['supplemental_source'] = source
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n')
    cap_path = registry / 'capabilities/etm.json'
    caps = json.loads(cap_path.read_text())
    caps['supplemental_operations'] = {
        'checkout_options': {'execution': 'integration_read', 'source': 'https://www.etm.ru/ipro3/cart',
                             'scope': 'Verified region, portal offices, requested destination, contract, payment and route discovery'},
        'order_checkout': {'execution': 'integration_write', 'source': 'https://www.etm.ru/ipro3/cart',
                           'scope': 'Portal checkout or public API customer request with contract, allocation and final document verification'}}
    for row in caps['capabilities']:
        if row['id'] != 'POST /invoice/create':
            continue
        compiled = contract['operations']['invoice_create']
        row.update(adapter='invoice_create', execution='integration_write',
                   effect='business_write', implementation_status='compiled_and_validated',
                   access='unknown_not_tested',
                   live_check={'status': 'not_tested', 'reason': 'No production orders created for deployment tests.'},
                   supplemental_source=source,
                   executable_contracts={'invoice_create': {
                       'params_schema': compiled['params_schema'], 'limits': compiled['limitations'],
                       'source': compiled['source'], 'supplemental_source': source}})
        row.pop('unsupported_reasons', None)
    cap_path.write_text(json.dumps(caps, ensure_ascii=False, indent=2) + '\n')

    cat_path = registry / 'catalog.json'
    cat = json.loads(cat_path.read_text())
    service = next(s for s in cat['services'] if s['id'] == 'etm')
    service['summary'] = 'Товары, цены, склады, заказы с договором и оплатой, документы и доставка.'
    service['adapter_status'] = 'Verified regional routing: portal checkout or public iPRO document workflow.'
    service['instructions'] = (
        'Для запроса «закажи» используй order_checkout через integration_write: это полный сценарий '
        'выбора магазина и договора, проверки цены, корзины и оплаты, оформления и сверки итоговых документов. '
        'Сначала integration_read checkout_options получает живые магазины, договоры и способы оплаты. '
        'Регион и магазин выбираются по поручению пользователя и проверяются через checkout_options. '
        'Параметры order_checkout плоские, приведены в write_operations. prepare не создаёт заказов или строк корзины; '
        'временное переключение региона проверяется и восстанавливается. Подготовка '
        'показывает товары, количество, лимит суммы, магазин, способ оплаты и договор. Если пользователь '
        'поручил оформить заказ и prepare вернул confirmation_required=false, сразу вызови execute '
        'для этого draft_id: поручение владельца достаточно, не проси ПОДТВЕРЖДАЮ, UUID или повторное согласие. '
        'Запрос посмотреть цену, наличие или статус не является командой оформить заказ. '
        'Уточняй только действительно недостающие условия; выполняй известные из переписки. '
        'При confirmation_required=true используй возвращённый механизм согласования. Для bill/bill требуется активный договор и '
        'доступный живой способ оплаты. Не обещай готовность к самовывозу по факту создания документа. '
        'Существующие чужие строки корзины не удаляются. При неизвестном результате POST не создавай '
        'повторный заказ; вызови status для прежнего draft_id. Все документы после разделения проверяются. '
        'Обычная закупка товара под заказ допускает allow_supplier_order=true с явным указанием этого '
        'в итоговом предложении. При поручении только со склада оставь false. Не увеличивай количество '
        'самостоятельно ради упаковки или минимальной партии. '
        'continuous_cut=true задавай только при явно запрошенном непрерывном отрезке, а не из одного '
        'упоминания количества метров. Сохраняй заданный пользователем предел суммы; если он не задавал '
        'предел, используй актуальную полную сумму корзины из prepare. Корзина сама округляет сумму, '
        'цена единицы может быть округлена отдельно. '
        'Регион подтверждается через /user/session/get после штатного переключения. '
        'Для офиса из списка корзины используется API сайта /api/ipro/basket/order с номером ЭТМ. '
        'Для другого проверенного офиса order_checkout готовит публичный API-маршрут; '
        'отсутствие офиса в корзине не означает запрета всего аккаунта. '
        'Публичный маршрут передаёт реальный номер/дату договора и проверяет привязку, '
        'распределение и все итоговые документы. Созданная спецификация не равна оформленному заказу. '
        'customer_order_number сохраняет номер владельца, а при его отсутствии коннектор '
        'создаёт стабильный номер клиентской заявки из UUID черновика и явно показывает его в preview. '
        'Это номер нашей системы, а не штатный номер ЭТМ. '
        'Публичные операции invoice_create/invoice_order/invoice_delivery и остальные доступны отдельно. '
        'Прямой invoice_create требует точного OrderNumber владельца или сохранённого клиентского номера коннектора; '
        'его параметры тела восстановлены из руководства ЭТМ «Работа с заказами» от 24.01.2025. '
        'DocumentFunctionCode C заменяет прежний заказ и условия, D означает отказ: это явно показывается '
        'в подтверждении. Публичный invoice_order не выбирает договор/оплату. '
        'Расширенные публичные методы принимают path/query/body/headers; точная схема через '
        'integration_catalog(view="capabilities",service="etm",capability_id=...). '
        'Товарные goods/price/remains читаются по коду ЭТМ. Публичный /catalog ранее возвращал 404; '
        'это не означает отсутствия оформления. /goods/{id}/remains не выбирает город. '
        'Используется существующий российский SOCKS 127.0.0.1:10929; при его отказе не менять VPN. '
        'Список счетов не подтверждает юридически значимый ЭДО, pay_sum означает остаток к оплате. '
        'Наличие реализации не доказывает live-write; фактический заказ сверять по результату провайдера.')
    service['operations']['checkout_options'] = {
        'effect': 'read', 'description': 'Подтверждённый регион, офис выдачи, договор, оплата и маршрут заказа; без бизнес-записи.',
        'params': {'region': 'string required: exact ETM region, Volgograd=34',
                   'pickup_store': 'string optional: office to inspect, Universitetsky 85=29100'}}
    writes = service.setdefault('write_operations', {})
    writes['invoice_create'] = {
        'summary': 'Создать, подтвердить, заменить или отменить документ по номеру клиента',
        'effect': 'business_write', 'capability_id': 'POST /invoice/create',
        'params': {'body': 'Exact schema: capabilities POST /invoice/create, executable_contracts.invoice_create'},
        'access': 'unknown_not_tested'}
    writes['order_checkout'] = {
        'summary': 'Оформить заказ в выбранный регион через корзину или публичный API с проверкой условий',
        'effect': 'business_write',
        'params': {
            'items': 'required array of {code: ETM product code string, quantity: positive number}',
            'region': 'required string ETM region code, Volgograd=34',
            'pickup_store': 'required string exact office in portal list or requested_pickup from checkout_options',
            'customer_order_number': 'optional owner customer reference; otherwise public route uses durable AI-<draft UUID> reference, not native ETM numbering',
            'contract_id': 'optional string exact active contract from checkout_options; default must be unambiguous',
            'payment_method': 'required string active method code, e.g. bill',
            'pay_type': 'required string corresponding method type, e.g. bill',
            'max_total': 'optional positive amount ceiling in RUB; otherwise prepare fixes its live quoted total',
            'note': 'optional order note',
            'continuous_cut': 'optional boolean require one allocated stock lot for the whole cable length',
            'allow_supplier_order': 'optional boolean; true for procurement from supplier, false for stock-only transfer; shown in preview'},
        'source': 'ETM website frontend, public order manual and authenticated regional discovery, 2026-10-07',
        'access': 'reads_verified_write_not_tested'}
    # Preserve concurrent service-release suffixes (for example wb-control).
    version_parts = cat['version'].split('+')
    version_parts = [p for p in version_parts if not p.startswith('etm-checkout')]
    version_parts.insert(1, 'etm-checkout.1')
    version_parts = [p for p in version_parts if not p.startswith('etm-region.')]
    version_parts.append('etm-region.1')
    cat['version'] = '+'.join(version_parts)
    cat_path.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    update()
