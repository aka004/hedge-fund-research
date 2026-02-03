"""
Screener API endpoint.
"""

from fastapi import APIRouter, HTTPException
from typing import List
from ..models.schemas import ScreenerRequest, ScreenerResponse, StockSummary
from ..core.database import get_db

router = APIRouter(prefix="/api", tags=["screener"])


def build_where_clause(filters: List) -> tuple[str, dict]:
    """Build SQL WHERE clause from filters."""
    conditions = []
    params = {}
    param_idx = 0
    
    for filter_obj in filters:
        field = filter_obj.field
        operator = filter_obj.operator
        value = filter_obj.value
        
        if operator == "eq":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} = ${param_name}")
            params[param_name] = value
            param_idx += 1
            
        elif operator == "ne":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} != ${param_name}")
            params[param_name] = value
            param_idx += 1
            
        elif operator == "lt":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} < ${param_name}")
            params[param_name] = value
            param_idx += 1
            
        elif operator == "gt":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} > ${param_name}")
            params[param_name] = value
            param_idx += 1
            
        elif operator == "lte":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} <= ${param_name}")
            params[param_name] = value
            param_idx += 1
            
        elif operator == "gte":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} >= ${param_name}")
            params[param_name] = value
            param_idx += 1
            
        elif operator == "between":
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError(f"between operator requires [min, max] array")
            param_min = f"p{param_idx}"
            param_max = f"p{param_idx + 1}"
            conditions.append(f"{field} BETWEEN ${param_min} AND ${param_max}")
            params[param_min] = value[0]
            params[param_max] = value[1]
            param_idx += 2
            
        elif operator == "in":
            if not isinstance(value, list):
                raise ValueError(f"in operator requires array")
            # DuckDB doesn't support parameterized IN clauses easily
            # Use multiple OR conditions instead
            or_conditions = []
            for v in value:
                param_name = f"p{param_idx}"
                or_conditions.append(f"{field} = ${param_name}")
                params[param_name] = v
                param_idx += 1
            conditions.append(f"({' OR '.join(or_conditions)})")
            
        elif operator == "contains":
            param_name = f"p{param_idx}"
            conditions.append(f"{field} ILIKE ${param_name}")
            params[param_name] = f"%{value}%"
            param_idx += 1
    
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    return where_clause, params


@router.post("/screener", response_model=ScreenerResponse)
async def screen_stocks(request: ScreenerRequest):
    """
    Filter and search stocks.
    
    Supports:
    - Filtering by multiple criteria
    - Full-text search on ticker/name
    - Sorting
    - Pagination
    """
    
    try:
        # Build WHERE clause from filters
        where_clause, params = build_where_clause(request.filters)
        
        # Add search condition
        if request.search:
            search_param = f"search"
            search_condition = f"(ticker ILIKE ${search_param} OR name ILIKE ${search_param})"
            params[search_param] = f"%{request.search}%"
            where_clause = f"({where_clause}) AND ({search_condition})"
        
        # Build ORDER BY clause
        order_clause = "market_cap DESC"  # default
        if request.sort:
            direction = request.sort.direction.upper()
            order_clause = f"{request.sort.field} {direction}"
        
        # Calculate offset
        offset = (request.page - 1) * request.page_size
        
        # Build query
        count_sql = f"""
        SELECT COUNT(*) as total
        FROM screener_summary
        WHERE {where_clause}
        """
        
        data_sql = f"""
        SELECT *
        FROM screener_summary
        WHERE {where_clause}
        ORDER BY {order_clause}
        LIMIT {request.page_size} OFFSET {offset}
        """
        
        with get_db() as conn:
            # Get total count
            count_result = conn.execute(count_sql, params).fetchone()
            total = count_result[0] if count_result else 0
            
            # Get data
            data_result = conn.execute(data_sql, params).fetchdf()
            
            # Convert to dict records
            records = data_result.to_dict('records')
            
            # Clean and convert to StockSummary objects
            stocks = []
            for row in records:
                # Clean the row - convert NaN/NA to None
                cleaned_row = {}
                for key, value in row.items():
                    if value is not None:
                        try:
                            import math
                            if isinstance(value, float) and math.isnan(value):
                                cleaned_row[key] = None
                            else:
                                cleaned_row[key] = value
                        except:
                            cleaned_row[key] = value
                    else:
                        cleaned_row[key] = None
                
                try:
                    stocks.append(StockSummary(**cleaned_row))
                except Exception as e:
                    # Log and skip problematic rows
                    print(f"Warning: Could not serialize row for {cleaned_row.get('ticker', 'unknown')}: {e}")
                    continue
            
            return ScreenerResponse(
                total=total,
                page=request.page,
                page_size=request.page_size,
                data=stocks
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
