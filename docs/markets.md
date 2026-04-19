> ## Documentation Index
> Fetch the complete documentation index at: https://docs.domeapi.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Markets

> Find markets on Polymarket using various filters including the ability to search



## OpenAPI

````yaml api-reference/openapi.json get /polymarket/markets
openapi: 3.0.3
info:
  title: Dome API
  description: APIs for prediction markets.
  version: 0.0.1
servers:
  - url: https://api.domeapi.io/v1
security: []
paths:
  /polymarket/markets:
    get:
      summary: Get Markets
      description: >-
        Fetches market data with optional filtering and search functionality.
        Supports filtering by market slug, condition ID, token ID, or tags, as
        well as fuzzy search across market titles and descriptions. Returns
        markets ordered by volume (most popular first) when filters are applied,
        or by start_time (most recent first) when no filters are provided.
      operationId: getMarkets
      parameters:
        - name: market_slug
          in: query
          required: false
          description: Filter markets by market slug(s). Can provide multiple values.
          schema:
            type: array
            items:
              type: string
            example:
              - bitcoin-up-or-down-july-25-8pm-et
          style: form
          explode: true
        - name: event_slug
          in: query
          required: false
          description: Filter markets by event slug(s). Can provide multiple values.
          schema:
            type: array
            items:
              type: string
            example:
              - presidential-election-winner-2028
          style: form
          explode: true
        - name: condition_id
          in: query
          required: false
          description: Filter markets by condition ID(s). Can provide multiple values.
          schema:
            type: array
            items:
              type: string
            example:
              - >-
                0x4567b275e6b667a6217f5cb4f06a797d3a1eaf1d0281fb5bc8c75e2046ae7e57
          style: form
          explode: true
        - name: token_id
          in: query
          required: false
          description: >-
            Filter markets by token ID(s). Matches markets where the token_id is
            either the primary_token_id or secondary_token_id. Can provide
            multiple values (maximum 100). Each token_id must be a numeric
            string.
          schema:
            type: array
            items:
              type: string
              pattern: ^[0-9]+$
            maxItems: 100
            example:
              - >-
                24891147099018724959141647991382271578149113344000019968758330059825991230807
          style: form
          explode: true
        - name: tags
          in: query
          required: false
          description: Filter markets by tag(s). Can provide multiple values.
          schema:
            type: array
            items:
              type: string
            example:
              - politics
              - crypto
          style: form
          explode: true
        - name: search
          in: query
          required: false
          description: >-
            Search markets by keywords in title and description. Must be URL
            encoded (e.g., 'bitcoin%20price' for 'bitcoin price').
          schema:
            type: string
            example: bitcoin
        - name: status
          in: query
          required: false
          description: Filter markets by status (whether they're open or closed)
          schema:
            type: string
            enum:
              - open
              - closed
            example: open
        - name: min_volume
          in: query
          required: false
          description: >-
            Filter markets with total trading volume greater than or equal to
            this amount (USD)
          schema:
            type: number
            example: 100000
        - name: limit
          in: query
          required: false
          description: >-
            Number of markets to return (1-100). Default: 10 for search, 10 for
            regular queries.
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 10
            example: 20
        - name: pagination_key
          in: query
          required: false
          description: >-
            Base64-encoded cursor for efficient pagination. Returned in the
            previous response's pagination object. Use this instead of large
            offsets for better performance.
          schema:
            type: string
            example: >-
              eyJzdGFydF9kYXRlIjoiMjAyNi0wMS0xOVQxMjowMDowMC4wMDBaIiwiY29uZGl0aW9uX2lkIjoiMHgxMjM0In0=
        - name: start_time
          in: query
          required: false
          description: Filter markets from this Unix timestamp in seconds (inclusive)
          schema:
            type: integer
            example: 1640995200
        - name: end_time
          in: query
          required: false
          description: Filter markets until this Unix timestamp in seconds (inclusive)
          schema:
            type: integer
            example: 1672531200
      responses:
        '200':
          description: Markets response with pagination
          content:
            application/json:
              schema:
                type: object
                properties:
                  markets:
                    type: array
                    items:
                      type: object
                      properties:
                        market_slug:
                          type: string
                          example: btc-updown-15m-1762516800
                        event_slug:
                          type: string
                          nullable: true
                          description: >-
                            The event slug this market belongs to, or null if
                            not associated with an event
                          example: presidential-election-winner-2028
                        condition_id:
                          type: string
                          example: >-
                            0x6876ac2b6174778c973c118aac287c49057c4d5360f896729209fe985a2c07fb
                        title:
                          type: string
                          example: Bitcoin Up or Down - November 7, 7:00AM-7:15AM ET
                        start_time:
                          type: integer
                          description: Unix timestamp in seconds when the market starts
                          example: 1762506140
                        end_time:
                          type: integer
                          description: Unix timestamp in seconds when the market ends
                          example: 1762517700
                        completed_time:
                          type: integer
                          nullable: true
                          description: >-
                            Unix timestamp in seconds when the market was
                            completed
                          example: null
                        close_time:
                          type: integer
                          nullable: true
                          description: Unix timestamp in seconds when the market was closed
                          example: null
                        game_start_time:
                          type: string
                          format: date-time
                          nullable: true
                          description: >-
                            Datetime string in UTC format (YYYY-MM-DD
                            HH:MM:SS.000) for when the game/event starts. Only
                            present for sports markets that have a game start
                            time.
                          example: '2025-08-16 20:00:00.000'
                        tags:
                          type: array
                          items:
                            type: string
                          example:
                            - Up or Down
                            - Crypto Prices
                            - Hide From New
                            - Recurring
                            - Crypto
                            - Bitcoin
                            - 15M
                        volume_1_week:
                          type: number
                          description: Trading volume in USD for the past week
                          example: 0
                        volume_1_month:
                          type: number
                          description: Trading volume in USD for the past month
                          example: 0
                        volume_1_year:
                          type: number
                          description: Trading volume in USD for the past year
                          example: 0
                        volume_total:
                          type: number
                          description: Total trading volume in USD
                          example: 93.148228
                        resolution_source:
                          type: string
                          description: URL to the data source used for market resolution
                          example: https://data.chain.link/streams/btc-usd
                        image:
                          type: string
                          description: URL to the market image
                          example: >-
                            https://polymarket-upload.s3.us-east-2.amazonaws.com/BTC+fullsize.png
                        description:
                          type: string
                          nullable: true
                          description: >-
                            Detailed description of the market, or null if no
                            description is available
                          example: >-
                            This market resolves to "Yes" if Bitcoin's price
                            increases from the start to the end of the 15-minute
                            window, and "No" otherwise.
                        negative_risk_id:
                          type: string
                          nullable: true
                          description: >-
                            Negative risk identifier for the market, or null if
                            not applicable
                          example: null
                        side_a:
                          type: object
                          description: First side/outcome of the market
                          properties:
                            id:
                              type: string
                              description: Token ID for side A
                              example: >-
                                14557944883400223565643640243919774851380876937588843424705199812983475639104
                            label:
                              type: string
                              description: Label for side A
                              example: Up
                        side_b:
                          type: object
                          description: Second side/outcome of the market
                          properties:
                            id:
                              type: string
                              description: Token ID for side B
                              example: >-
                                57567439101367774829602299916701968079591032322820664013819223989961583069589
                            label:
                              type: string
                              description: Label for side B
                              example: Down
                        winning_side:
                          type: string
                          nullable: true
                          description: >-
                            The winning side of the market (null if not yet
                            resolved)
                          example: null
                        status:
                          type: string
                          enum:
                            - open
                            - closed
                          example: open
                        extra_fields:
                          type: object
                          description: >-
                            Additional market-specific fields as a map of
                            key-value pairs. For updown markets (markets with
                            slugs containing '-updown-15m-', '-up-or-down-', or
                            '-updown-4h-'), this object includes 'price_to_beat'
                            and 'final_price' fields. Empty object if no extra
                            fields are present.
                          additionalProperties:
                            nullable: true
                            anyOf:
                              - type: number
                              - type: string
                              - type: boolean
                          example:
                            price_to_beat: 98765.43
                            final_price: 98801.21
                  pagination:
                    type: object
                    properties:
                      limit:
                        type: integer
                        example: 20
                      total:
                        type: integer
                        description: Total number of markets matching the filters
                        example: 150
                      has_more:
                        type: boolean
                        description: Whether there are more markets available
                        example: true
                      pagination_key:
                        type: string
                        description: >-
                          Cursor for next page. Only present when has_more is
                          true and using cursor-based pagination.
                        example: >-
                          eyJ2b2x1bWVfdG90YWwiOjEyMzQ1LjY3LCJjbG9zZV90aW1lIjpudWxsLCJjb25kaXRpb25faWQiOiIweDEyMzQifQ==
        '400':
          description: Bad Request - Invalid parameters or validation errors
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
                    example: Invalid search parameter
                  message:
                    type: string
                    example: search must be at least 2 characters long
              examples:
                search_too_short:
                  summary: Search query too short
                  value:
                    error: Invalid search parameter
                    message: search must be at least 2 characters long
                search_with_other_params:
                  summary: Search with other parameters
                  value:
                    error: Invalid query parameters
                    message: >-
                      search parameter cannot be used with other filter
                      parameters
                invalid_limit:
                  summary: Invalid limit
                  value:
                    error: Invalid limit parameter
                    message: limit must be a number between 1 and 100
        '500':
          description: Internal Server Error
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
                    example: Internal Server Error
                  message:
                    type: string
                    example: Failed to fetch markets data

````
