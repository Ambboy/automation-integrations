ETM checkout contract research, verified 2026-10-04

Public sources only. No account responses, cookies, credentials, session keys,
private document identifiers or customer contracts are stored in this directory.

Sources:
- https://ipro.etm.ru/ns2000/yaml/cli.yaml (live-openapi-2026-10-04.yaml)
- https://www.etm.ru/ipro3/cart
- https://www.etm.ru/_next/static/chunks/pages/_app-94a07acbe8d3823e.js
  Targeted public modules are copied as frontend-module-*.js.txt.
- https://www.etm.ru/_next/static/chunks/pages/ipro3/cart-9786f4fd245a8908.js
  The page maps response createdDoc[].invnum to invoice document IDs.
- ETM_Order_24_01_25.pdf: vendor-provided Order API document cached in the
  established server etm-ipro skill cache (2026-09-11); create pages 5-8 are
  extracted separately. The precise original download URL was not retained.

Verified portal flow (internal website API, not public supported API parity):
1. POST /api/ipro/user/login multipart fields log,pwd,city,user-id.
   The same existing API credentials work. Keep session only in memory.
   Following requests send the session-id HEADER and city cookie.
2. GET /api/ipro/basket/functionality supplies available form controls and
   sendKey names. Contract is i_dogovor; note is tovzak in the verified account.
3. GET /api/ipro/basket/order?rows=100&group=1&skl=<office>&page=1&i_dogovor=<contract>
   returns selected office, pickupAvailable, exact basket rows/delivery_parts,
   cartVersion, selection, sum, restrictions. Read every page. A source warehouse
   from goods/remains does not prove the pickup office.
4. GET /api/ipro/goods/<code>/price?type=etm&city=<region>&skl=<office>
   returns account pricewnds. /goods/<code> provides product/pack metadata;
   /goods/<code>/packs?city=<region>&skl=<office> provides conditional packing
   restrictions. packMinPartSuppl is a supplier minimum, not a factory reel size.
5. GET /api/ipro/payment/methods?region=<region>&store=<office>&to_pay=<sum>&i_dogovor=<contract>
   yields rows[].pay_meth with payment_method_code, paytype and active status.
6. After exact authorization only: POST /api/ipro/basket/add multipart gds,val,city.
   Do not clear or add over unrelated lines; read quantities back to catch rounding.
7. After exact allocation/ceiling/payment/contract revalidation:
   POST /api/ipro/basket/order multipart fields from dynamic functionality plus
   skl,payment_method_code,pay-type,application=ipro3. No custom OrderNumber.
8. Persist createdDoc[].invnum immediately, then read EVERY final body and exact
   invoice-list record. body.store and list.st_code are current/source warehouses;
   list.st_dest is the receiving warehouse. Verify buyer INN/KPP, quantities,
   document status and contractual pay_title/pay_date. A split specification is
   not completed procurement. Accepted order is not proof of pickup readiness.
9. Critical notes can be POSTed to /invoice/<id>/ps (text, service_message=false)
   for all final documents and then GET/read back as complete text.

Operational limits:
- Never retry an uncertain basket or order mutation automatically.
- Read-only prepare cannot allocate stock or promise a physical continuous cut.
- Blank/null/zero source IDs do not prove stock. Supplier authorization does not
  establish one continuous cut. Account remains can still report a different city.
- /info/stores?class17=<region> returned empty rows in the live check. Options uses
  checkout-offered offices, and describes them as such, not an exhaustive city list.
- Login sometimes omits buyer INN/KPP; the implementation verifies them from a
  current account invoice body whose cli_code and document ID match its list row.
- Deployment verification used authentication, discovery, and quote preparation
  only. No basket mutation, production checkout, payment or live order was tested.
