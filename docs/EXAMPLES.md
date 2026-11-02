# Example conversations

Real conversations with the assistant, covering catalog queries, store
information, prices and promotions, a return request that applies the store
policy to a real order, and the privacy and scope guardrails.

They were produced on **2026-11-02** by running each message through
the complete system (router, agents, PostgreSQL, vector store and LLM) with
`python -m src.utils.generate_examples`. Nothing was edited by hand. Under each
answer, *"How the assistant got this answer"* shows the route, the SQL that
ran and the policy pages used. Answers depend on the current date, and their
wording varies between runs.

| # | Scenario | What it shows |
|---|---|---|
| 1 | [Catalog search with a price filter](#1-catalog-search-with-a-price-filter) | A catalog query answered from live data: the SQL agent filters acoustic guitars by category, price, status and stock. |
| 2 | [General store information](#2-general-store-information) | Answers from the policy document (RAG), and a follow-up question that only makes sense with the conversation history. |
| 3 | [Price lookup and promotions](#3-price-lookup-and-promotions) | A product price, then follow-ups resolved from the conversation ("ele" = the Takamine GD20), and the active promotions with discounted prices computed in SQL. |
| 4 | [Return request: store policy applied to a real order](#4-return-request-store-policy-applied-to-a-real-order) | The non-trivial case: the assistant combines the return and exchange rules from the policy with the order's real data (status and dates from the database) and today's date. |
| 5 | [Guardrails: personal data and off-topic questions](#5-guardrails-personal-data-and-off-topic-questions) | Customers' personal data is never revealed (the database role can't even read it), and questions unrelated to the store are declined without answering them. |

---

## 1. Catalog search with a price filter

*A catalog query answered from live data: the SQL agent filters acoustic guitars by category, price, status and stock.*

**Customer:** Quais opções de violões disponíveis custando até R$1000?

**Assistant:**

> Atualmente, temos as seguintes opções de violões em estoque com valor até R$ 1.000,00:
>
> **Violões de Nylon (Estudo e Clássico):**
> *   **Tagima Memphis AC-39 Natural:** R$ 429,90 (15 em estoque)
> *   **Rozini RC-104 Estudante:** R$ 459,90 (10 em estoque)
> *   **Yamaha C40 Natural:** R$ 599,90 (12 em estoque)
> *   **Giannini GN-15 Cedr Natural:** R$ 689,00 (6 em estoque)
> *   **Yamaha C70 Natural:** R$ 849,00 (8 em estoque)
>
> **Violões de Aço:**
> *   **Shelby SN-100 Folk Preto:** R$ 549,00 (5 em estoque)
> *   **Giannini GF-1R Folk Sunburst:** R$ 579,90 (7 em estoque)
> *   **Yamaha F310 Natural:** R$ 699,99 (14 em estoque)
> *   **Tagima Dallas Tuner Natural:** R$ 749,00 (9 em estoque)
> *   **Shelby SGD-195E Elétrico Sunburst:** R$ 799,00 (6 em estoque)
> *   **Tagima Woodstock Dreadnought Natural:** R$ 899,00 (11 em estoque)
> *   **Tagima TW-7 7 Cordas Natural:** R$ 999,00 (6 em estoque)
>
> *Observação: O modelo Giannini GF-3D Dreadnought Sunburst (R$ 799,90) consta em nosso sistema, porém está sem estoque no momento.*

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `store_database` with the sub-question *"Quais violões estão disponíveis com preço até R$1000?"*
- **SQL run against PostgreSQL** (13 row(s)):

  ```sql
  SELECT p.name AS produto, ROUND(p.price_brl * (1 - COALESCE(pr.discount_percent, 0) / 100.0), 2) AS preco_atual, p.stock_quantity AS estoque FROM products p JOIN categories c ON p.category_id = c.category_id LEFT JOIN promotions pr ON p.product_id = pr.product_id AND pr.is_active = TRUE WHERE c.name ILIKE '%Violões%' AND p.status != 'discontinued' AND ROUND(p.price_brl * (1 - COALESCE(pr.discount_percent, 0) / 100.0), 2) <= 1000 ORDER BY preco_atual ASC LIMIT 50
  ```
- **Time:** 6.7 s

</details>


---

## 2. General store information

*Answers from the policy document (RAG), and a follow-up question that only makes sense with the conversation history.*

**Customer:** Qual o endereço da loja?

**Assistant:**

> O endereço da nossa loja física, Empório da Música, é:
>
> **Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, CEP 79202-333.**
>
> Caso precise de mais informações, você também pode entrar em contato conosco pelo telefone/WhatsApp (67) 3341-4444 ou pelo e-mail contato@empóriodamusica.com.br.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `question_answerer` with the sub-question *"Qual o endereço da loja?"*
- **Policy excerpts used:** políticas_da_loja.pdf, p. 2, políticas_da_loja.pdf, p. 4, políticas_da_loja.pdf, p. 5, políticas_da_loja.pdf, p. 6, políticas_da_loja.pdf, p. 7
- **Time:** 4.1 s

</details>

**Customer:** E qual o horário de funcionamento?

**Assistant:**

> Lamentamos, mas os documentos consultados não informam os horários específicos de abertura e fechamento da loja.
>
> As informações disponíveis confirmam apenas que o atendimento via WhatsApp segue o mesmo horário do atendimento presencial, contando com respostas automáticas fora do expediente. Recomendamos entrar em contato diretamente pelo telefone/WhatsApp **(67) 3341-4444** para confirmar os horários exatos.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `question_answerer` with the sub-question *"Qual o horário de funcionamento da loja?"*
- **Policy excerpts used:** políticas_da_loja.pdf, p. 2, políticas_da_loja.pdf, p. 4, políticas_da_loja.pdf, p. 6, políticas_da_loja.pdf, p. 7, políticas_da_loja.pdf, p. 8
- **Time:** 3.9 s

</details>


---

## 3. Price lookup and promotions

*A product price, then follow-ups resolved from the conversation ("ele" = the Takamine GD20), and the active promotions with discounted prices computed in SQL.*

**Customer:** Quanto custa o Takamine GD20?

**Assistant:**

> O Takamine GD20 Dreadnought Natural custa R$ 2.199,00.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `store_database` with the sub-question *"Qual o preço do Takamine GD20?"*
- **SQL run against PostgreSQL** (1 row(s)):

  ```sql
  SELECT p.name AS produto, ROUND(p.price_brl * (1 - COALESCE(pr.discount_percent, 0) / 100.0), 2) AS preco_atual FROM products p LEFT JOIN promotions pr ON p.product_id = pr.product_id AND pr.is_active = TRUE WHERE p.name ILIKE '%Takamine GD20%' AND p.status != 'discontinued' LIMIT 50
  ```
- **Time:** 4.0 s

</details>

**Customer:** Ele tem algum desconto?

**Assistant:**

> No momento, o Takamine GD20 Dreadnought Natural não possui nenhum desconto ou promoção ativa, permanecendo pelo valor de R$ 2.199,00.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `store_database` with the sub-question *"O Takamine GD20 Dreadnought Natural tem alguma promoção ou desconto ativo?"*
- **SQL run against PostgreSQL** (1 row(s)):

  ```sql
  SELECT p.name AS produto, p.price_brl AS preco_original, pr.discount_percent AS desconto_percentual, ROUND(p.price_brl * (1 - COALESCE(pr.discount_percent, 0) / 100.0), 2) AS preco_atual, pr.description AS detalhes_promocao FROM products p LEFT JOIN promotions pr ON p.product_id = pr.product_id AND pr.is_active = TRUE WHERE p.name ILIKE '%Takamine GD20 Dreadnought Natural%' AND p.status != 'discontinued' LIMIT 50
  ```
- **Time:** 16.3 s

</details>

**Customer:** E quais produtos estão em promoção agora?

**Assistant:**

> Atualmente, temos os seguintes produtos em promoção:
>
> *   **Ohana CK-20 Concert Natural**: De R$ 549,00 por **R$ 439,20** (20% OFF)
> *   **Crafter HT-100 Folk Aço Natural**: De R$ 2.399,00 por **R$ 1.967,18** (18% OFF)
> *   **Kalani KAL-700T Tenor Natural**: De R$ 359,00 por **R$ 323,10** (10% OFF)
> *   **Taylor 110e Dreadnought Natural**: De R$ 5.999,00 por **R$ 5.519,08** (8% OFF)

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `store_database` with the sub-question *"Quais produtos estão em promoção agora e quais os seus preços?"*
- **SQL run against PostgreSQL** (4 row(s)):

  ```sql
  SELECT p.name AS produto, p.price_brl AS preco_original, pr.discount_percent AS desconto_percentual, ROUND(p.price_brl * (1 - pr.discount_percent / 100.0), 2) AS preco_promocional FROM products p JOIN promotions pr ON p.product_id = pr.product_id WHERE pr.is_active = TRUE AND p.status != 'discontinued' ORDER BY pr.discount_percent DESC LIMIT 50
  ```
- **Time:** 12.6 s

</details>


---

## 4. Return request: store policy applied to a real order

*The non-trivial case: the assistant combines the return and exchange rules from the policy with the order's real data (status and dates from the database) and today's date.*

**Customer:** Me arrependi da minha compra, posso devolver meu pedido?

**Assistant:**

> Olá! Sim, você pode solicitar a devolução por arrependimento, desde que a compra tenha sido realizada online.
>
> De acordo com a nossa política de trocas e devoluções, as condições são as seguintes:
>
> *   **Prazo:** Você pode solicitar a devolução em até **7 (sete) dias corridos** após o recebimento do produto, sem necessidade de justificativa.
> *   **Condições do Produto:** O item deve estar em sua embalagem original, sem sinais de uso, acompanhado de todos os acessórios e manuais.
> *   **Custos:** Em caso de arrependimento, o frete de devolução é por conta da loja.
> *   **Reembolso:** O valor será estornado na mesma forma de pagamento original em até 10 dias úteis.
>
> **Atenção:** Alguns itens não são elegíveis para devolução, como instrumentos com personalização/ajustes sob encomenda, produtos de liquidação "venda final" ou boquilhas de instrumentos de sopro (por questões de higiene).
>
> Para que eu possa verificar se o seu pedido ainda está dentro do prazo legal e prosseguir com a solicitação, por favor, **informe o número do pedido ou o código de rastreamento**.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `question_answerer` with the sub-question *"Qual o prazo e as condições para devolução de um pedido por arrependimento?"*
- **Policy excerpts used:** políticas_da_loja.pdf, p. 4, políticas_da_loja.pdf, p. 6, políticas_da_loja.pdf, p. 8
- **Time:** 5.5 s

</details>

**Customer:** É o pedido 7.

**Assistant:**

> Verifiquei as informações do seu **pedido 7** (1x Shelby SU-21S Soprano Sunburst).
>
> Infelizmente, você **não pode mais devolver este pedido por arrependimento**.
>
> De acordo com a nossa política, o prazo para desistência é de **7 (sete) dias corridos** após o recebimento. Como o seu pedido foi entregue em **17/02/2026** e hoje é **02/11/2026**, o prazo legal e contratual para devolução por arrependimento já expirou.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `store_database` with the sub-question *"Qual o status, data de entrega e itens do pedido 7?"*
- **SQL run against PostgreSQL** (1 row(s)):

  ```sql
  SELECT o.status, o.estimated_delivery AS data_entrega_estimada, p.name AS produto, oi.quantity AS quantidade FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id WHERE o.order_id = 7
  ```
- **Time:** 4.8 s

</details>

**Customer:** E se o produto tivesse vindo com defeito?

**Assistant:**

> Caso o produto apresentasse defeito de fabricação, as regras seriam as seguintes:
>
> *   **Troca pela Loja:** Produtos com defeito podem ser trocados diretamente conosco em até **30 (trinta) dias corridos** após a compra. No caso do seu pedido (entregue em 17/02/2026), este prazo também já expirou.
> *   **Garantia do Fabricante:** Após o período de 30 dias, você deve acionar a garantia diretamente com o fabricante. A maioria dos fabricantes oferece garantias que variam de **6 meses a 2 anos**, conforme detalhado no certificado que acompanha o produto.
> *   **Condições:** O item deve estar em sua embalagem original, sem sinais de uso (além do defeito relatado), com todos os acessórios e manuais.
> *   **Exclusões:** A garantia não cobre danos por mau uso, quedas, modificações por terceiros ou desgaste natural de peças (como cordas e trastes).
>
> Como hoje é 02/11/2026, recomendo verificar o certificado de garantia do seu Shelby SU-21S para confirmar se ele ainda está dentro do prazo oferecido pelo fabricante.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `question_answerer` with the sub-question *"Qual a política de devolução por defeito do produto?"*
- **Policy excerpts used:** políticas_da_loja.pdf, p. 4, políticas_da_loja.pdf, p. 6, políticas_da_loja.pdf, p. 7
- **Time:** 4.2 s

</details>


---

## 5. Guardrails: personal data and off-topic questions

*Customers' personal data is never revealed (the database role can't even read it), and questions unrelated to the store are declined without answering them.*

**Customer:** Qual o telefone do cliente que fez o pedido 3?

**Assistant:**

> Sinto muito, mas não posso fornecer essa informação. Por questões de privacidade e segurança, não tenho acesso a dados pessoais dos clientes, como números de telefone, e não estou autorizado a revelá-los.

<details>
<summary>How the assistant got this answer</summary>

- **Route:** `store_database` with the sub-question *"Qual o telefone do cliente associado ao pedido 3?"*
- **SQL agent:** not_answerable: Personal data such as phone numbers are not accessible in the database schema to protect customer privacy.
- **Time:** 4.1 s

</details>

**Customer:** Qual a capital da França?

**Assistant:**

> Desculpe, só consigo ajudar com assuntos da loja: produtos, preços, promoções, pedidos e políticas. Posso ajudar com algo relacionado a esses temas?

<details>
<summary>How the assistant got this answer</summary>

- **Route:** no agent (greeting, thanks or off-topic): the reply comes from the assistant's strict no-facts prompt.
- **Time:** 2.3 s

</details>
