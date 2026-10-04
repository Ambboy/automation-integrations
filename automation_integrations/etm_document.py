"""Supplement the incomplete iPRO OpenAPI from ETM's Order integration manual.

The provider's OpenAPI lists invoice/create with a null body schema. The Order
manual describes that body separately. A caller's OrderNumber is visible on the
document, not an idempotency token; native ETM numbering uses website checkout.
"""
from decimal import Decimal


SOURCE = 'ETM API. Работа с заказами, revision 24.01.2025, pages 4–9'


def body_schema():
    def text(length=None, **extra):
        return {'type': 'string', **({'maxLength': length} if length else {}), **extra}

    def obj(properties, required=()):
        return {'type': 'object', 'properties': properties, 'additionalProperties': False,
                **({'required': list(required)} if required else {})}

    integer = {'anyOf': [{'type': 'integer', 'minimum': 1},
                         text(pattern=r'^[1-9][0-9]*\Z')]}
    amount = {'anyOf': [{'type': 'number', 'minimum': 0},
                        text(pattern=r'^[0-9]+(?:\.[0-9]+)?\Z')]}
    day = text(format='date')
    party = obj({'ILN': text()})
    line = obj({
        'LineNumber': integer, 'EAN': text(13, pattern=r'^[0-9]+\Z'),
        'BuyerItemCode': text(minLength=1), 'SupplierItemCode': text(minLength=1),
        'ManufacturerArticle': text(minLength=1), 'ManufacturerCod': text(minLength=1),
        'ItemDescription': text(), 'ItemType': text(), 'OrderedQuantity': amount,
        'UnitOfMeasure': text(minLength=1), 'ExpectedDeliveryDate': day,
        **{name: amount for name in ('OrderedUnitNetPrice', 'OrderedUnitGrossPrice',
                                    'NetAmount', 'GrossAmount', 'TaxRate')},
    }, ('LineNumber', 'OrderedQuantity'))
    line['anyOf'] = [{'required': [name]} for name in
                    ('SupplierItemCode', 'BuyerItemCode', 'ManufacturerArticle')]
    line['dependentRequired'] = {'ManufacturerArticle': ['ManufacturerCod']}
    return obj({
        'OrderNumber': text(minLength=1, pattern=r'^[0-9A-ZБ-ЯЁ./-]+\Z'),
        'OrderDate': day, 'ExpectedDeliveryDate': day, 'ContractNumber': text(),
        'ContractDate': day, 'Currency': text(3, pattern=r'^[A-Z]{3}\Z'),
        'DocumentFunctionCode': {'type': 'string', 'enum': ['P', 'A', 'D', 'C']},
        'Remarks': text(), 'Buyer': party,
        'Seller': obj({'ILN': {'const': '4660011519999'}, 'CodeByBuyer': text()}, ('ILN',)),
        'DeliveryPoint': party, 'Invoicee': party,
        'Order-Lines': {'type': 'array', 'minItems': 1, 'items': line},
        'TotalLines': integer,
        **{name: amount for name in ('TotalOrderedAmount', 'TotalNetAmount',
                                    'TotalGrossAmount', 'TotalTaxAmount')},
    }, ('OrderNumber', 'DocumentFunctionCode', 'Seller', 'Order-Lines'))


def validate_body(body):
    """Cross-field checks after schema validation; no generated business numbers."""
    lines = body['Order-Lines']
    numbers = [str(line['LineNumber']) for line in lines]
    if len(set(numbers)) != len(numbers):
        raise ValueError('duplicate_line_number')
    if 'TotalLines' in body and int(body['TotalLines']) != len(lines):
        raise ValueError('total_lines_mismatch')
    if any(Decimal(str(line['OrderedQuantity'])) <= 0 for line in lines):
        raise ValueError('invalid_order_quantity')


def supplement(row):
    """Apply only to the known null-schema operation, preserving raw provenance."""
    if row['id'] != 'POST /invoice/create':
        return row
    row['params_schema']['properties']['body'] = body_schema()
    required = row['params_schema'].setdefault('required', [])
    if 'body' not in required:
        required.append('body')
    row['unsupported_reason'] = None
    row['supplemental_contract_source'] = SOURCE
    row['limitations'] = [
        'OrderNumber is the visible customer document number. Never invent it; '
        'use website order_checkout for native ETM numbering and payment selection.',
        'DocumentFunctionCode C cancels the old document and creates a new one; '
        'D refuses the existing order. Include this business effect in the preview.',
        'Creation alone does not prove pickup, payment terms or delivery. Read every '
        'returned data.id/data.ids[].docid and any subsequent split document.',
        'The manual marks ItemDescription required in its table but omits it in its '
        'own SupplierItemCode example; this contract accepts that documented example.',
        'ManufacturerCod follows the field table; prose also spells it ManufacturerCode. '
        'Prefer a verified SupplierItemCode when ordering a known product.',
    ]
    return row


def preview_details(body):
    """Expose replacement/cancellation even though they share the create route."""
    actions = {
        'P': 'Разместить первичный заказ',
        'A': 'Подтвердить ранее размещённый заказ',
        'D': 'Отказаться от ранее размещённого заказа',
        'C': 'Заменить ранее размещённый заказ и согласованные условия; '
             'ЭТМ присвоит новый ID документа',
    }
    return {'business_action': actions[body['DocumentFunctionCode']],
            'affected_order_number': body['OrderNumber']}
