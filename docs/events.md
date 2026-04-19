> ## Documentation Index
> Fetch the complete documentation index at: https://docs.domeapi.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Events

> List events (groups of related markets) on Polymarket with filtering by category and status



## OpenAPI

````yaml api-reference/openapi.json get /polymarket/events
openapi: 3.0.3
info:
  title: Dome API
  description: APIs for prediction markets.
  version: 0.0.1
servers:
  - url: https://api.domeapi.io/v1
security: []
paths:
  /polymarket/events:
    get:
      summary: Get Events
      description: >-
        Fetches events (groups of related markets) with optional filtering by
        event_slug, tags/categories and status. Events aggregate multiple
        markets under a single topic (e.g., 'Presidential Election 2024'
        contains multiple candidate markets). Returns events ordered by total
        volume (most popular first).


        **Example Request (single event by slug):**

        ```bash

        curl
        'https://api.domeapi.io/v1/polymarket/events?event_slug=presidential-election-winner-2024&include_markets=true'

        ```


        **Example Request (filter by tags):**

        ```bash

        curl
        'https://api.domeapi.io/v1/polymarket/events?tags=sports&status=open&limit=10'

        ```


        **Example Request (with markets included):**

        ```bash

        curl
        'https://api.domeapi.io/v1/polymarket/events?include_markets=true&limit=5'

        ```
      operationId: getEvents
      parameters:
        - name: event_slug
          in: query
          required: false
          description: >-
            Filter by specific event slug. When provided, returns a single
            hydrated event matching that slug (e.g.,
            'presidential-election-winner-2024'). Use with include_markets=true
            to get the full event with all its markets.
          schema:
            type: string
            example: presidential-election-winner-2024
        - name: tags
          in: query
          required: false
          description: >-
            Filter events by tag(s)/category. Can provide multiple values (e.g.,
            sports, crypto, politics).
          schema:
            type: array
            items:
              type: string
            example:
              - sports
              - football
          style: form
          explode: true
        - name: status
          in: query
          required: false
          description: >-
            Filter events by status. An event is 'open' if any of its markets
            are still open, 'closed' if all markets are closed.
          schema:
            type: string
            enum:
              - open
              - closed
            example: open
        - name: include_markets
          in: query
          required: false
          description: >-
            Set to 'true' to include the list of markets for each event in the
            response.
          schema:
            type: string
            enum:
              - 'true'
              - 'false'
            default: 'false'
            example: 'true'
        - name: start_time
          in: query
          required: false
          description: Filter events starting after this Unix timestamp (seconds)
          schema:
            type: integer
            example: 1640995200
        - name: end_time
          in: query
          required: false
          description: Filter events starting before this Unix timestamp (seconds)
          schema:
            type: integer
            example: 1672531200
        - name: game_start_time
          in: query
          required: false
          description: >-
            Filter events by game start time (Unix timestamp in seconds). Useful
            for filtering sports events by when the game starts.
          schema:
            type: integer
            example: 1704067200
        - name: limit
          in: query
          required: false
          description: 'Number of events to return (1-100). Default: 10.'
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 10
            example: 10
        - name: pagination_key
          in: query
          required: false
          description: >-
            Pagination key for cursor-based pagination. Use the value from the
            previous response's pagination.pagination_key field to get the next
            page of results. Do not use the deprecated 'offset' parameter.
          schema:
            type: string
            example: >-
              eyJsYXN0Vm9sdW1lIjoxNzEyMTMyNjYzLjk2MTYwNjMsImxhc3RFdmVudFNsdWciOiJuYmEtY2hhbXBpb24tMjAyNC0yMDI1In0=
      responses:
        '200':
          description: Events response with pagination
          content:
            application/json:
              schema:
                type: object
                properties:
                  events:
                    type: array
                    items:
                      type: object
                      properties:
                        event_slug:
                          type: string
                          description: Unique identifier for the event
                          example: presidential-election-winner-2024
                        title:
                          type: string
                          description: Event title
                          example: Presidential Election Winner 2024
                        subtitle:
                          type: string
                          nullable: true
                          description: Event subtitle or description
                          example: Who will win the 2024 US Presidential Election?
                        status:
                          type: string
                          enum:
                            - open
                            - closed
                          description: >-
                            Event status - 'open' if any market is open,
                            'closed' if all markets are closed
                          example: closed
                        start_time:
                          type: integer
                          description: Unix timestamp (seconds) when the event started
                          example: 1704067200
                        end_time:
                          type: integer
                          description: Unix timestamp (seconds) when the event ends
                          example: 1730851200
                        volume_fiat_amount:
                          type: number
                          description: >-
                            Total trading volume across all markets in the event
                            (USD)
                          example: 3686335059.29
                        settlement_sources:
                          type: string
                          nullable: true
                          description: Resolution/settlement source for the event
                          example: Associated Press
                        rules_url:
                          type: string
                          nullable: true
                          description: URL to the event rules (if available)
                          example: null
                        image:
                          type: string
                          nullable: true
                          description: Event image URL
                          example: https://polymarket.com/images/election-2024.png
                        tags:
                          type: array
                          items:
                            type: string
                          description: Array of category tags for the event
                          example:
                            - politics
                            - elections
                        market_count:
                          type: integer
                          description: Number of markets in this event
                          example: 17
                        markets:
                          type: array
                          description: >-
                            List of markets in this event (only included when
                            include_markets=true)
                          items:
                            type: object
                            properties:
                              market_slug:
                                type: string
                                example: will-trump-win-2024
                              title:
                                type: string
                                example: Will Trump win the 2024 election?
                              condition_id:
                                type: string
                                example: 0x1234...
                              status:
                                type: string
                                enum:
                                  - open
                                  - closed
                                example: closed
                              volume_total:
                                type: number
                                example: 1500000000
                  pagination:
                    type: object
                    properties:
                      limit:
                        type: integer
                        description: Number of events returned in this response
                        example: 10
                      has_more:
                        type: boolean
                        description: >-
                          Whether there are more events available. If true, use
                          pagination_key to fetch the next page.
                        example: true
                      pagination_key:
                        type: string
                        nullable: true
                        description: >-
                          Pagination key for fetching the next page. Pass this
                          value as the pagination_key query parameter to get the
                          next page of results. Will be null if has_more is
                          false.
                        example: >-
                          eyJsYXN0Vm9sdW1lIjoxNzEyMTMyNjYzLjk2MTYwNjMsImxhc3RFdmVudFNsdWciOiJuYmEtY2hhbXBpb24tMjAyNC0yMDI1In0=
        '400':
          description: Bad Request - Invalid parameters
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string
                    example: Invalid status parameter
                  message:
                    type: string
                    example: status must be 'open' or 'closed'
              examples:
                invalid_status:
                  summary: Invalid status
                  value:
                    error: Invalid status parameter
                    message: status must be 'open' or 'closed'
                invalid_limit:
                  summary: Invalid limit
                  value:
                    error: Invalid limit parameter
                    message: limit must be a number between 1 and 100
                invalid_offset:
                  summary: Invalid offset
                  value:
                    error: Invalid offset parameter
                    message: offset must be a non-negative number
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
                    example: Failed to fetch events data

````
